; rom dumping program
; assemble with fasmg

include 'include/ez80.inc'
include 'include/ti84pceg.inc'
include 'include/tiformat.inc'
format ti executable 'DUMP'

maxsize := 65512
certloc := $3b0000

dump:
	ld	hl,$10101
	call	ti.EnoughMem
	ret	c
	call	ti.ClrScrn
	ld	hl,name
	ld	bc,3
	call	create
	ex	de,hl
	ld	de,(ti.OSSize + 1)
	ld	(hl),de
	call	ti.Arc_Unarc
	ld	hl,num
	ld	(hl),'1'
	push	hl
	ld	hl,name
	ld	bc,maxsize
	call	create
	ld	hl,certloc
	ldir
	call	ti.Arc_Unarc
	pop	hl
	ld	(hl),'A'-1
loop:
	call	ti.HomeUp
	ld	hl,segstr
	call	ti.PutS
	ld	a,(num)
	inc	a
	ld	(num),a
	call	ti.PutC
	ld	a,'.'
	call	ti.PutC
	call	ti.PutC
	call	ti.PutC
	ld	hl,name
	ld	bc,maxsize
	push	bc
	call	create
addr:
	ld	hl,0
	push	hl
	ldir
	pop	hl
	pop	bc
	add	hl,bc
	ld	(addr + 1),hl
	push	hl
	call	ti.Arc_Unarc
	pop	hl
	ld	de,(ti.OSSize + 1)
	or	a,a
	sbc	hl,de
	jr	c,loop
	call	ti.HomeUp
	jp	ti.ClrScrn

; input:
;  hl -> name
;  bc = size
; output:
;  de -> location
;  bc = size
;  op1 = name
create:
	push	bc
	push	bc
	push	hl
	call	ti.Mov9ToOP1
	call	ti.ChkFindSym
	call	nc,ti.DelVarArc
	pop	hl
	call	ti.Mov9ToOP1
	pop	hl
	call	ti.CreateAppVar
	push	de
	call	ti.OP4ToOP1
	pop	de
	inc	de
	inc	de
	pop	bc
	ret

name:
	db	ti.AppVarObj, "ROMData"
num:
	db	"0"
segstr:
	db	"Dumping Segment ", 0
