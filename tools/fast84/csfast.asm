; SPDX-License-Identifier: MIT
; CSFAST: CalcSuite's "Fast mode" for the TI-84 Plus CE (OS 5.0 - 5.4; plain eZ80 assembly,
; no toolchain libraries). Copyright (c) 2026 Paul Kratky. MIT licence (see LICENSE).
;
; Run it once: it installs a raw key hook (the OS's "GetKey" hook) and returns. Run it again: it
; removes the hook and deletes everything it made. A RAM reset removes the hook too (the
; archived copy of its code, ZZHOOK, is then inert; the PC deletes it with "fast off").
;
; The hook does nothing for ordinary keys (three compares). When the PC presses one of two key
; codes the OS doesn't use (sent as a remote key over USB), the hook swallows that key and
; compresses the screen (VRAM, 320 x 240 RGB565) into RAM AppVars the PC then downloads with
; the normal variable request:
;   0x22  a full frame         0x23  a delta: only the rows that changed since the last frame
;
; What it makes (all ours; nothing of the user's is touched):
;   ZZHOOK  archived AppVar: the hook's code (the hook runs from the archive, where it stays put
;           until a garbage collection; the OS skips a hook whose first byte isn't 83h)
;   CSSNAP  RAM AppVar, 2048 bytes: header, the first 2030 bytes of the frame, a seq stamp
;   ZZSNPA..ZZSNPH  RAM AppVars, 4096 bytes each: a seq stamp, the next 4092 bytes of the frame,
;           a seq stamp (as many of them as leave 16 KB of RAM free, at most 8)
;   ZZWORK  RAM AppVar, 3584 bytes: the hook's scratch (row hashes, one row of runs) and a
;           copy of the hook's code, run from there (from the archive it is several times slower)
;
; CSSNAP's layout (after the AppVar's own 2-byte size):
;   0  'CSN1'          4  u16 seq_begin    6  u16 seq_end (= seq_begin when the frame is whole)
;   8  u8 kind: 0 full frame, 2 delta, 1 too big / not 16 bpp (take a normal screenshot),
;               4 installed but no frame yet, 5 being written
;   9  u8 ZZSNP chunks there are (bit 7: taken when the OS was idle)  10 u16 base seq (a delta applies to the frame of that seq)
;   12 u24 payload length (from offset 16)                   15 u8 ZZSNP chunks this frame used
;   16 payload: 30 bytes, one bit per row (row r: byte r/8, bit r%8) set when the row is sent;
;      then for each sent row, top to bottom, two halves of 160 pixels, each as runs of
;      (u8 count-1, u16 colour little endian); a run never crosses a half.
;   The payload continues in ZZSNPA (byte 2030 on), ZZSNPB (byte 2030 + 4092 on), ...
;   Stamps: CSSNAP's last 2 bytes and each chunk's first and last 2 bytes hold the frame's seq.
;
; Build: fasmg with the CE toolchain's commands.alm and ez80.alm (tools/fast84/build.py).
; OS addresses: CE-Programming toolchain, src/include/ti84pceg.inc (v14.2).

include 'commands.alm'
include 'ez80.alm'

assume adl = 1

; ---- OS 5.x entry points and RAM ----
_Mov9ToOP1      := 020320h
_MemChk         := 0204FCh
_ChkFindSym     := 02050Ch
_EnoughMem      := 02051Ch
_PutS           := 0207C0h
_NewLine        := 0207F0h
_CreateAppVar   := 021330h
_DelVarArc      := 021434h
_Arc_Unarc      := 021448h
_ChkInRam       := 021F98h
_FindFreeArcSpot := 022078h
OP1             := 0D005F8h
rawKeyHookPtr   := 0D025DBh
cxCurApp        := 0D007E0h     ; the context: its key code (kQuit = the home screen)
kQuit           := 040h
getKeyHookPtr   := 0D025DEh     ; the GetCSC hook's pointer
hookflags2      := 34h          ; (iy+): bit 5 = raw key hook active, bit 0 = GetCSC hook active
rawKeyHookActive := 5
getCSCHookActive := 0
userMem         := 0D1A881h
mpLcdUpbase     := 0E30010h
mpLcdCtrl       := 0E30018h
AppVarObj       := 15h

; ---- Ours ----
TRIG_FULL       := 22h
TRIG_DELTA      := 23h
TRIG_NOW        := 24h          ; a delta at once, from the raw key hook (the fallback)
SNAP_SIZE       := 2048
CHUNK_SIZE      := 4096
MAX_CHUNKS      := 8
WORK_SIZE       := 3584
HDR             := 16
BITMAP          := 30
RESERVE         := 16384        ; RAM left free for the user, at least
VERSION         := 1

; ZZWORK's layout (W = its data, after the size)
W_P0     := 0       ; u24 CSSNAP data
W_P      := 1984    ; u24 x 8 ZZSNPA..H data
W_N      := 21      ; u8 chunks found
W_OUT    := 22      ; u24 where the next payload byte goes
W_LEFT   := 25      ; u24 bytes left in this chunk
W_IDX    := 28      ; u8 the chunk being written (0 = CSSNAP)
W_ROW    := 29      ; u8
W_SRC    := 30      ; u24 the next row's pixels
W_MODE   := 33      ; u8 0 full, 1 delta
W_SEQ    := 34      ; u16 the last frame's seq
W_VALID  := 36      ; u8 1 when the row hashes match the last frame the PC was given
W_ROWS   := 40      ; u8 rows sent
W_FLAGS  := 49      ; u8 hookflags2 at the last trigger (diagnostics)
W_OLDFLAG := 38     ; u8 hookflags2 when the GetCSC hook was armed
W_IEF    := 39      ; u8 the flags of "ld a, i": bit 2 = interrupts were on
W_OLDCSC := 53      ; u24 the GetCSC hook pointer then
W_HOW    := 37      ; u8 the trigger; bit 7 when the GetCSC hook took the picture
W_BASE   := 41      ; u24 where the hook runs: its copy at W + W_CODE
W_COUNT  := 46      ; u24 bytes still to copy
W_LEN    := 50      ; u24 this row's run bytes
W_TOTAL  := 56      ; u24 payload length
W_HPTR   := 60      ; u24 this row's hash
W_HASH   := 64      ; 240 x 4 bytes: Fletcher sums of each row's pixels
W_RUNS   := 1024    ; one row's runs (at most 320 x 3 = 960 bytes)
W_CODE   := 2048    ; the hook's copy: code in RAM runs much faster than from the archive

	org	userMem - 2
	db	0EFh, 07Bh

start:
	call	is_ours
	jp	z, uninstall
	bit	rawKeyHookActive, (iy + hookflags2)
	jp	z, install
	ld	hl, msg_other
	jp	print

; Z when our hook is the active raw key hook
is_ours:
	bit	rawKeyHookActive, (iy + hookflags2)
	jr	z, .no
	ld	hl, (rawKeyHookPtr)
	ld	a, (hl)
	cp	a, 083h
	ret	nz
	inc	hl
	inc	hl
	inc	hl
	ld	de, hook + 3
	ld	b, 8
.cmp:
	ld	a, (de)
	cp	a, (hl)
	ret	nz
	inc	hl
	inc	de
	djnz	.cmp
	ret
.no:
	or	a, 1
	ret

uninstall:
	bit	getCSCHookActive, (iy + hookflags2)
	jr	z, .csc
	ld	hl, (getKeyHookPtr)     ; Our GetCSC hook, armed and not yet run: off too
	ld	de, (rawKeyHookPtr)
	or	a, a
	sbc	hl, de
	jr	c, .csc
	ld	de, HOOK_LEN
	sbc	hl, de
	jr	nc, .csc
	res	getCSCHookActive, (iy + hookflags2)
	ld	hl, nm_work             ; Put back the GetCSC hook there was before (ZZWORK has it)
	call	_Mov9ToOP1
	call	_ChkFindSym
	jr	c, .csc
	call	_ChkInRam
	jr	nz, .csc
	ex	de, hl
	inc	hl
	inc	hl
	push	hl
	pop	ix
	ld	hl, (ix + W_OLDCSC)
	ld	(getKeyHookPtr), hl
	bit	getCSCHookActive, (ix + W_OLDFLAG)
	jr	z, .csc
	set	getCSCHookActive, (iy + hookflags2)
.csc:
	res	rawKeyHookActive, (iy + hookflags2)
	call	delete_work
	ld	hl, nm_hook
	call	delete_var
	ld	hl, msg_off
	jp	print

install:
	call	delete_work
	; The hook's code: reuse an archived ZZHOOK that is byte for byte this one
	ld	hl, nm_hook
	call	_Mov9ToOP1
	call	_ChkFindSym
	jr	c, .make
	call	_ChkInRam
	jr	z, .remake
	call	hook_in_archive
	jr	z, .have
.remake:
	ld	hl, nm_hook
	call	delete_var
.make:
	ld	hl, HOOK_LEN + 64
	call	_EnoughMem
	jp	c, no_ram
	ld	bc, HOOK_LEN + 64
	cp	a, a
	call	_FindFreeArcSpot
	jp	z, no_archive
	ld	hl, nm_hook
	call	_Mov9ToOP1
	ld	hl, HOOK_LEN
	call	_CreateAppVar
	inc	de
	inc	de
	ld	hl, hook
	ld	bc, HOOK_LEN
	ldir
	ld	hl, nm_hook
	call	_Mov9ToOP1
	call	_Arc_Unarc
	ld	hl, nm_hook
	call	_Mov9ToOP1
	call	_ChkFindSym
	jp	c, no_archive
	call	_ChkInRam
	jp	z, no_archive
	call	hook_in_archive
	jp	nz, no_archive
.have:
	ld	(hook_addr), hl
	; The frame's AppVars: CSSNAP, ZZWORK, then as many ZZSNPn as leave RESERVE bytes free
	call	_MemChk
	ld	de, SNAP_SIZE + WORK_SIZE + 64 + RESERVE
	or	a, a
	sbc	hl, de
	jp	c, no_ram
	ld	de, CHUNK_SIZE + 32
	ld	b, 0
.count:
	ld	a, b
	cp	a, MAX_CHUNKS
	jr	nc, .counted
	or	a, a
	sbc	hl, de
	jr	c, .counted
	inc	b
	jr	.count
.counted:
	ld	a, b
	ld	(chunks), a
	ld	hl, nm_work
	ld	bc, WORK_SIZE
	call	make_var
	ld	hl, nm_snap
	ld	bc, SNAP_SIZE
	call	make_var
	ex	de, hl                  ; The header: ready, no frame yet
	ld	(hl), 'C'
	inc	hl
	ld	(hl), 'S'
	inc	hl
	ld	(hl), 'N'
	inc	hl
	ld	(hl), '1'
	inc	hl
	inc	hl
	inc	hl
	inc	hl
	inc	hl
	ld	(hl), 4
	inc	hl
	ld	a, (chunks)
	ld	(hl), a
	ld	a, 0
.chunk:
	ld	hl, chunks
	cp	a, (hl)
	jr	nc, .hook
	push	af
	ld	hl, nm_chunk
	call	_Mov9ToOP1
	pop	af
	push	af
	add	a, 'A'
	ld	(OP1 + 6), a
	ld	hl, 0
	ld	bc, CHUNK_SIZE
	call	make_var_op1
	pop	af
	inc	a
	jr	.chunk
.hook:
	ld	hl, (hook_addr)
	ld	(rawKeyHookPtr), hl
	set	rawKeyHookActive, (iy + hookflags2)
	ld	hl, msg_on
	jr	print

no_ram:
	ld	hl, msg_ram
	jr	print
no_archive:
	ld	hl, msg_arc
print:
	call	_PutS
	jp	_NewLine

; In: DE = an archived ZZHOOK's VAT data pointer (from _ChkFindSym). Out: HL = its code,
; Z when it is this hook byte for byte.
hook_in_archive:
	ex	de, hl
	ld	bc, 9                   ; The archive entry's header, then its name
	add	hl, bc
	ld	c, (hl)
	inc	hl
	add	hl, bc
	ld	c, (hl)                 ; The AppVar's size
	inc	hl
	ld	b, (hl)
	inc	hl
	ld	a, c
	cp	a, HOOK_LEN and 0FFh
	ret	nz
	ld	a, b
	cp	a, HOOK_LEN shr 8
	ret	nz
	push	hl
	ld	de, hook
	ld	bc, HOOK_LEN
.cmp:
	ld	a, (de)
	cp	a, (hl)
	jr	nz, .diff
	inc	hl
	inc	de
	dec	bc
	ld	a, c
	or	a, b
	jr	nz, .cmp
	pop	hl
	ret
.diff:
	pop	hl
	ret

; HL = a 9-byte name, BC = size: deletes any old one, makes it, fills it with zeros.
; Out: DE = its data (after the size)
make_var:
	push	bc
	push	hl
	call	delete_var
	pop	hl
	call	_Mov9ToOP1
	pop	bc
make_var_op1:
	push	bc
	push	bc
	pop	hl
	call	_CreateAppVar
	inc	de
	inc	de
	pop	bc
	push	de
	ex	de, hl
	ld	(hl), 0
	dec	bc
	push	hl
	pop	de
	inc	de
	ldir
	pop	de
	ret

; HL = a 9-byte name: deletes it (RAM or archive) when it's there
delete_var:
	call	_Mov9ToOP1
	call	_ChkFindSym
	ret	c
	jp	_DelVarArc

delete_work:
	ld	hl, nm_snap
	call	delete_var
	ld	hl, nm_work
	call	delete_var
	ld	a, 'A'
.chunks:
	push	af
	ld	hl, nm_chunk
	call	_Mov9ToOP1
	pop	af
	push	af
	ld	(OP1 + 6), a
	call	_ChkFindSym
	call	nc, _DelVarArc
	pop	af
	inc	a
	cp	a, 'A' + MAX_CHUNKS
	jr	nz, .chunks
	ret

nm_hook:	db	AppVarObj, 'ZZHOOK', 0, 0
nm_work:	db	AppVarObj, 'ZZWORK', 0, 0
nm_snap:	db	AppVarObj, 'CSSNAP', 0, 0
nm_chunk:	db	AppVarObj, 'ZZSNPA', 0, 0
msg_on:		db	'Fast mode ON', 0
msg_off:	db	'Fast mode OFF', 0
msg_other:	db	'Fast: another key hook on', 0
msg_ram:	db	'Fast: not enough RAM', 0
msg_arc:	db	'Fast: archive full', 0
hook_addr:	dl	0
chunks:		db	0

; ---- The hook. It runs from the archive at an address only known then, so it is position
; independent: relative jumps only, and a far jump goes through the address it runs at (W_BASE:
; its copy in ZZWORK). ----

; A jump to a label in the hook's RAM copy (destroys HL and DE; IX = W)
macro hjp target
	ld	hl, (ix + W_BASE)
	ld	de, target - hook
	add	hl, de
	jp	(hl)
end macro

; The raw key hook (rawKeyHookPtr). A trigger key isn't turned into a frame here: while the OS
; handles a key it shows its busy indicator and hides the cursor, so a picture taken now would
; never show the cursor. The trigger arms a one-shot GetCSC hook instead, which takes the
; picture the next time the OS waits for a key (cursor and all), then switches itself off.
; Only when another program's GetCSC hook is on does the picture come from here.
hook:
	db	083h
	jr	.go
	db	'CSFASTHK'              ; is_ours and the PC look for this
	db	VERSION
.go:
	cp	a, TRIG_FULL
	jr	z, .arm
	cp	a, TRIG_DELTA
	jr	z, .arm
	cp	a, TRIG_NOW
	jr	z, .now
	or	a, a                    ; Any other key: as it is
	ret
.arm:
	or	a, 040h                 ; Bit 6: arm the GetCSC hook (h_ram)
	jr	.home
.now:
	ld	a, TRIG_DELTA           ; A picture right now (busy indicator on, no cursor)
.home:
	; Only on the home screen (its menus included): elsewhere (graph, table, Y=, mode, an
	; editor...) the OS leaves the screen for the home screen as soon as the link reads a
	; variable. So no picture there: the key is swallowed at once, and the PC, seeing it
	; answered in ~25 ms rather than ~100, takes a normal screenshot and reads nothing.
	push	af
	ld	a, (cxCurApp)
	cp	a, kQuit
	jr	nz, .away
	pop	af
	jr	h_snap_now
.away:
	pop	af
	xor	a, a
	ret

; The one-shot GetCSC hooks: A = 1Ah before the OS scans the keypad, 1Bh after (B = the scan
; code, passed on as it is)
csc_full:
	db	083h
	cp	a, 01Ah
	jr	z, .go
	ld	a, b
	ret
.go:
	ld	a, TRIG_FULL or 080h    ; Bit 7: from the GetCSC hook
	jr	csc_snap
csc_delta:
	db	083h
	cp	a, 01Ah
	jr	z, .go
	ld	a, b
	ret
.go:
	ld	a, TRIG_DELTA or 080h
csc_snap:
	res	getCSCHookActive, (iy + hookflags2)  ; One shot (h_ram puts back the one before)
	push	hl                      ; The picture returns to csc_ret
	push	de
	ld	hl, (rawKeyHookPtr)
	ld	de, csc_ret - hook
	add	hl, de
	pop	de
	ex	(sp), hl
	jr	h_snap_now
csc_ret:                                ; On to the GetCSC hook there was before ours, if any
	bit	getCSCHookActive, (iy + hookflags2)
	jr	z, .plain
	push	hl
	ld	hl, (getKeyHookPtr)
	ld	a, (hl)
	cp	a, 083h
	jr	nz, .plainhl
	inc	hl
	ex	(sp), hl
	ld	a, 01Ah
	ret                             ; = jp (its code), every register as the OS gave them
.plainhl:
	pop	hl
.plain:
	ld	a, 01Ah                 ; NZ, A = 1Ah: the OS scans as usual
	or	a, a
	ret

; A = the trigger (bit 6: only arm the GetCSC hook; bit 7: called from it). Returns A = 0, Z
; (the key swallowed), every other register as it was.
h_snap_now:
	push	bc
	push	de
	push	hl
	push	ix
	ld	hl, (OP1)               ; OP1 as it was (12 bytes, the last one is OP2's first)
	push	hl
	ld	hl, (OP1 + 3)
	push	hl
	ld	hl, (OP1 + 6)
	push	hl
	ld	hl, (OP1 + 9)
	push	hl
	push	af                      ; The trigger
	ld	hl, (rawKeyHookPtr)
	ld	de, h_work - hook
	add	hl, de
	call	_Mov9ToOP1
	call	_ChkFindSym
	jr	c, .none0
	call	_ChkInRam
	jr	nz, .none0
	ex	de, hl
	ld	a, (hl)                 ; ZZWORK must be WORK_SIZE
	cp	a, WORK_SIZE and 0FFh
	jr	nz, .none0
	inc	hl
	ld	a, (hl)
	cp	a, WORK_SIZE shr 8
	jr	nz, .none0
	inc	hl
	push	hl
	pop	ix                      ; IX = W from here on
	ld	de, W_CODE              ; The hook into RAM, and on there
	add	hl, de
	ex	de, hl
	ld	(ix + W_BASE), de
	ld	hl, (rawKeyHookPtr)
	ld	bc, HOOK_LEN
	ldir
	hjp	h_ram
.none0:                                 ; Not set up (a RAM reset?): the key does nothing
	ld	hl, (rawKeyHookPtr)
	ld	de, h_out_pop - hook
	add	hl, de
	jp	(hl)

h_ram:
	pop	af
	push	af
	ld	(ix + W_HOW), a
	ld	b, (iy + hookflags2)
	ld	(ix + W_FLAGS), b       ; For the PC's diagnostics
	bit	6, a
	jr	z, .noarm
	; Arm: the GetCSC hook takes the picture when the OS is idle again. The one there was
	; (OS 5.4 has one of its own) is kept, put back by ours and called on.
	ld	(ix + W_OLDFLAG), b
	ld	hl, (getKeyHookPtr)
	ld	(ix + W_OLDCSC), hl
	ld	hl, (rawKeyHookPtr)
	ld	de, csc_full - hook
	and	a, 03Fh
	cp	a, TRIG_FULL
	jr	z, .full
	ld	de, csc_delta - hook
.full:
	add	hl, de
	ld	(getKeyHookPtr), hl
	set	getCSCHookActive, (iy + hookflags2)
	hjp	h_out_pop
.noarm:
	bit	7, a
	jr	z, .nocsc
	ld	hl, (ix + W_OLDCSC)     ; From the GetCSC hook: the one before back
	ld	(getKeyHookPtr), hl
	bit	getCSCHookActive, (ix + W_OLDFLAG)
	jr	z, .nocsc
	set	getCSCHookActive, (iy + hookflags2)
.nocsc:
	and	a, 03Fh
	sub	a, TRIG_FULL            ; 0 full, 1 delta
	ld	b, (ix + W_VALID)
	inc	b
	dec	b
	jr	nz, .mode
	xor	a, a                    ; No good hashes: a full frame whatever was asked
.mode:
	ld	(ix + W_MODE), a
	; CSSNAP
	ld	hl, (ix + W_BASE)
	ld	de, h_snap - hook
	add	hl, de
	push	ix
	call	_Mov9ToOP1
	call	_ChkFindSym
	pop	ix
	jr	c, .none
	push	de
	push	ix
	call	_ChkInRam
	pop	ix
	pop	hl
	jr	nz, .none
	ld	a, (hl)
	cp	a, SNAP_SIZE and 0FFh
	jr	nz, .none
	inc	hl
	ld	a, (hl)
	cp	a, SNAP_SIZE shr 8
	jr	nz, .none
	inc	hl
	ld	(ix + W_P0), hl
	ld	de, 9
	add	hl, de
	ld	a, (hl)                 ; The chunks the installer made
	and	a, 0Fh
	cp	a, MAX_CHUNKS + 1
	jr	c, .nok
	ld	a, MAX_CHUNKS
.nok:
	ld	(ix + W_N), a
	xor	a, a
	ld	(ix + W_IDX), a
	jr	.chunks
.none:                                  ; Not set up (a RAM reset?): the key does nothing
	hjp	h_out_pop
.chunks:
	ld	a, (ix + W_IDX)
	cp	a, (ix + W_N)
	jr	nc, .found
	ld	hl, (ix + W_BASE)
	ld	de, h_chunk - hook
	add	hl, de
	push	ix
	call	_Mov9ToOP1
	pop	ix
	ld	a, (ix + W_IDX)
	add	a, 'A'
	ld	(OP1 + 6), a
	push	ix
	call	_ChkFindSym
	pop	ix
	jr	c, .found
	push	de
	push	ix
	call	_ChkInRam
	pop	ix
	pop	de
	jr	nz, .found
	ld	a, (de)                 ; Must be CHUNK_SIZE (its low byte is 0)
	or	a, a
	jr	nz, .found
	inc	de
	ld	a, (de)
	cp	a, CHUNK_SIZE shr 8
	jr	nz, .found
	inc	de
	ld	a, (ix + W_IDX)
	push	ix
	pop	hl
	ld	bc, W_P
	add	hl, bc
	ld	bc, 3
.slot:
	or	a, a
	jr	z, .put
	add	hl, bc
	dec	a
	jr	.slot
.put:
	ld	(hl), de
	inc	(ix + W_IDX)
	jr	.chunks
.found:
	ld	a, (ix + W_IDX)
	ld	(ix + W_N), a
	; The header: being written
	ld	hl, (ix + W_P0)
	ld	e, (ix + W_SEQ)
	ld	d, (ix + W_SEQ + 1)
	inc	de
	inc	hl
	inc	hl
	inc	hl
	inc	hl
	ld	(hl), e                 ; seq_begin = the new seq
	inc	hl
	ld	(hl), d
	inc	hl
	dec	de
	ld	(hl), e                 ; seq_end = the old one until the end
	inc	hl
	ld	(hl), d
	inc	hl
	ld	(hl), 5
	; 16 bpp, at a whole frame in RAM?
	ld	a, (mpLcdCtrl)
	and	a, 00Eh
	cp	a, 00Ch
	jr	nz, .big
	ld	hl, (mpLcdUpbase)
	ld	de, 0D00000h
	or	a, a
	sbc	hl, de
	jr	c, .big
	ld	de, 040001h
	or	a, a
	sbc	hl, de
	jr	nc, .big
	ld	hl, (mpLcdUpbase)
	ld	(ix + W_SRC), hl
	jr	.rows
.big:
	hjp	h_big
.rows:
	; The row bitmap: all clear
	ld	hl, (ix + W_P0)
	ld	de, HDR
	add	hl, de
	ld	b, BITMAP
.clr:
	ld	(hl), 0
	inc	hl
	djnz	.clr
	ld	(ix + W_OUT), hl
	ld	hl, SNAP_SIZE - HDR - BITMAP - 2   ; The last 2 bytes: a seq stamp
	ld	(ix + W_LEFT), hl
	xor	a, a
	ld	(ix + W_IDX), a
	ld	(ix + W_ROW), a
	ld	(ix + W_ROWS), a
	ld	hl, BITMAP
	ld	(ix + W_TOTAL), hl
	lea	hl, ix + W_HASH
	ld	(ix + W_HPTR), hl

h_row:
	; The row's checksum first, so a row that didn't change costs about a third of making its
	; runs: Fletcher sums of 24-bit words read by popping them (the fastest read the eZ80 has),
	; 642 bytes from the row's start (2 of the next row's too: harmless). SP points into the
	; screen meanwhile, so interrupts are off for the row (about 0.2 ms); the code puts back SP
	; and IX by writing them into its own instructions (it runs from RAM, see W_CODE).
	ld	hl, (ix + W_BASE)
	ld	de, .pix + 2 - hook     ; "ld ix, nnnnnn" is DD 21 nn nn nn
	add	hl, de
	ld	(hl), ix
	ld	hl, (ix + W_BASE)
	ld	de, .psp + 1 - hook     ; "ld sp, nnnnnn" is 31 nn nn nn
	add	hl, de
	ex	de, hl
	ld	hl, 0
	add	hl, sp
	ex	de, hl
	ld	(hl), de
	ld	a, i                    ; P/V = interrupts on
	push	af
	pop	bc
	ld	(ix + W_IEF), c
	ld	hl, (ix + W_SRC)
	di
	ld	sp, hl
	ld	hl, 0                   ; s1
	ld	ix, 0                   ; s2
	ld	b, 107
.sum:
	pop	de
	add	hl, de
	ex	de, hl
	add	ix, de
	ex	de, hl
	pop	de
	add	hl, de
	ex	de, hl
	add	ix, de
	ex	de, hl
	djnz	.sum
.psp:
	ld	sp, 0
	push	ix
	pop	de                      ; DE = s2, HL = s1
.pix:
	ld	ix, 0
	bit	2, (ix + W_IEF)
	jr	z, .dis
	ei
.dis:
	ex	de, hl                  ; DE = s1, HL = s2
	push	hl
	pop	bc                      ; BC = s2
	ld	hl, (ix + W_HPTR)
	ld	a, (ix + W_MODE)
	or	a, a
	jr	z, .changed
	ld	a, (hl)
	cp	a, e
	jr	nz, .changed
	inc	hl
	ld	a, (hl)
	cp	a, d
	jr	nz, .changed
	inc	hl
	ld	a, (hl)
	cp	a, c
	jr	nz, .changed
	inc	hl
	ld	a, (hl)
	cp	a, b
	jr	nz, .changed
	hjp	h_next
.changed:
	ld	hl, (ix + W_HPTR)
	ld	(hl), e
	inc	hl
	ld	(hl), d
	inc	hl
	ld	(hl), c
	inc	hl
	ld	(hl), b
	inc	(ix + W_ROWS)
	; The row into runs at W + W_RUNS: two halves of 160 pixels
	push	ix
	ld	hl, (ix + W_SRC)
	ld	de, W_RUNS
	add	ix, de
	ld	a, 2
.half:
	push	af
	ld	b, 160
.run:
	ld	e, (hl)
	inc	hl
	ld	d, (hl)
	inc	hl
	ld	c, b
	dec	b
	jr	z, .emit
.same:
	ld	a, (hl)
	cp	a, e
	jr	nz, .emit
	inc	hl
	ld	a, (hl)
	cp	a, d
	jr	nz, .hi
	inc	hl
	djnz	.same
	jr	.emit
.hi:
	dec	hl
.emit:
	ld	a, c
	sub	a, b
	dec	a
	ld	(ix + 0), a
	ld	(ix + 1), e
	ld	(ix + 2), d
	lea	ix, ix + 3
	ld	a, b
	or	a, a
	jr	nz, .run
	pop	af
	dec	a
	jr	nz, .half
	; IX = the end of the runs; the length
	push	ix
	pop	de
	pop	ix
	lea	hl, ix + 0
	ld	bc, W_RUNS
	add	hl, bc
	ex	de, hl
	or	a, a
	sbc	hl, de
	ld	(ix + W_LEN), hl
	; Its bit in the bitmap
	ld	a, (ix + W_ROW)
	ld	c, a
	srl	a
	srl	a
	srl	a
	ld	hl, (ix + W_P0)
	ld	de, HDR
	add	hl, de
	ld	de, 0
	ld	e, a
	add	hl, de
	ld	a, c
	and	a, 7
	ld	b, a
	inc	b
	ld	a, 1
.bit:
	dec	b
	jr	z, .set
	add	a, a
	jr	.bit
.set:
	or	a, (hl)
	ld	(hl), a
	; The total
	ld	hl, (ix + W_TOTAL)
	ld	de, (ix + W_LEN)
	add	hl, de
	ld	(ix + W_TOTAL), hl
	; Copy the runs into the payload, chunk by chunk
	ld	hl, (ix + W_LEN)
	ld	(ix + W_COUNT), hl
	lea	hl, ix + 0
	ld	de, W_RUNS
	add	hl, de                  ; HL = the runs
h_copy:
	ld	a, (ix + W_LEFT)
	or	a, (ix + W_LEFT + 1)
	or	a, (ix + W_LEFT + 2)
	jr	nz, .room
	ld	a, (ix + W_IDX)         ; This chunk is full: the next one
	cp	a, (ix + W_N)
	jr	nc, .big
	inc	(ix + W_IDX)
	push	hl
	push	ix
	pop	hl
	ld	bc, W_P
	add	hl, bc
	ld	bc, 3
.slot:
	or	a, a
	jr	z, .got
	add	hl, bc
	dec	a
	jr	.slot
.got:
	ld	hl, (hl)
	inc	hl                      ; After its seq stamp
	inc	hl
	ld	(ix + W_OUT), hl
	ld	hl, CHUNK_SIZE - 4      ; And before the one at its end
	ld	(ix + W_LEFT), hl
	pop	hl
	jr	h_copy
.big:
	hjp	h_big
.room:
	push	hl                      ; The runs still to copy
	ld	bc, (ix + W_COUNT)
	ld	hl, (ix + W_LEFT)
	or	a, a
	sbc	hl, bc                  ; left - count
	jr	c, .part
	ld	(ix + W_LEFT), hl       ; All of it fits
	pop	hl
	ld	de, (ix + W_OUT)
	ldir
	ld	(ix + W_OUT), de
	jr	h_next
.part:
	ex	de, hl                  ; count - left are left over
	or	a, a
	sbc	hl, hl
	sbc	hl, de
	ld	(ix + W_COUNT), hl
	ld	bc, (ix + W_LEFT)
	or	a, a
	sbc	hl, hl
	ld	(ix + W_LEFT), hl
	pop	hl
	ld	de, (ix + W_OUT)
	ldir
	ld	(ix + W_OUT), de
	jr	h_copy

h_next:
	ld	hl, (ix + W_SRC)
	ld	de, 640
	add	hl, de
	ld	(ix + W_SRC), hl
	ld	hl, (ix + W_HPTR)
	ld	de, 4
	add	hl, de
	ld	(ix + W_HPTR), hl
	inc	(ix + W_ROW)
	ld	a, (ix + W_ROW)
	cp	a, 240
	jr	z, h_done
	hjp	h_row

h_done:
	ld	hl, (ix + W_P0)
	ld	de, 8
	add	hl, de
	ld	a, (ix + W_MODE)
	add	a, a                    ; 0 full, 2 delta
	ld	(hl), a
	inc	hl
	ld	a, (ix + W_HOW)         ; Bit 7 of byte 9: taken when the OS was idle (GetCSC hook)
	and	a, 080h
	or	a, (ix + W_N)
	ld	(hl), a
	dec	hl
	inc	hl
	inc	hl
	ld	a, (ix + W_SEQ)         ; base seq: the frame before
	ld	(hl), a
	inc	hl
	ld	a, (ix + W_SEQ + 1)
	ld	(hl), a
	inc	hl
	ld	de, (ix + W_TOTAL)
	ld	(hl), de
	inc	hl
	inc	hl
	inc	hl
	ld	a, (ix + W_IDX)
	ld	(hl), a
	ld	a, 1
	ld	(ix + W_VALID), a
	jr	h_seq

h_big:                                  ; Too big, or not a 16 bpp screen: the PC takes a shot
	xor	a, a
	ld	(ix + W_VALID), a       ; The hashes no longer match what the PC has
	ld	hl, (ix + W_P0)
	ld	de, 8
	add	hl, de
	ld	(hl), 1
	ld	de, 4
	add	hl, de
	ld	de, 0
	ld	(hl), de

h_seq:                                  ; The new seq, written last as seq_end
	ld	l, (ix + W_SEQ)
	ld	h, (ix + W_SEQ + 1)
	inc	hl
	ld	(ix + W_SEQ), l
	ld	(ix + W_SEQ + 1), h
	; Seq stamps: CSSNAP's last 2 bytes, each chunk used: its first 2 and its last 2. The PC
	; takes a frame only when every stamp it read is this seq (a var read while a picture was
	; being taken, or a chunk left from another frame, shows up as a stamp that differs).
	ex	de, hl                  ; DE = seq
	ld	hl, (ix + W_P0)
	ld	bc, SNAP_SIZE - 2
	add	hl, bc
	ld	(hl), e
	inc	hl
	ld	(hl), d
	ld	a, (ix + W_IDX)         ; Chunks used
	push	ix
	pop	hl
	ld	bc, W_P
	add	hl, bc
.stamp:
	or	a, a
	jr	z, .stamped
	push	af
	push	hl
	ld	hl, (hl)
	ld	(hl), e
	inc	hl
	ld	(hl), d
	ld	bc, CHUNK_SIZE - 3
	add	hl, bc
	ld	(hl), e
	inc	hl
	ld	(hl), d
	pop	hl
	inc	hl
	inc	hl
	inc	hl
	pop	af
	dec	a
	jr	.stamp
.stamped:
	ld	hl, (ix + W_P0)         ; seq_end last
	ld	bc, 6
	add	hl, bc
	ld	(hl), e
	inc	hl
	ld	(hl), d

h_out_pop:
	pop	af
	pop	hl
	ld	(OP1 + 9), hl
	pop	hl
	ld	(OP1 + 6), hl
	pop	hl
	ld	(OP1 + 3), hl
	pop	hl
	ld	(OP1), hl
	pop	ix
	pop	hl
	pop	de
	pop	bc
	xor	a, a                    ; The trigger key is swallowed
	ret

h_work:		db	AppVarObj, 'ZZWORK', 0, 0
h_snap:		db	AppVarObj, 'CSSNAP', 0, 0
h_chunk:	db	AppVarObj, 'ZZSNPA', 0, 0

HOOK_LEN := $ - hook

assert HOOK_LEN <= WORK_SIZE - W_CODE
