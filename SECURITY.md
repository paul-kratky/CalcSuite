# Security

## Reporting a problem

If you find a security problem in CalcSuite, please report it privately:
<https://github.com/paul-kratky/CalcSuite/security/advisories/new> (the repository's
**Security** tab, **Report a vulnerability**). Please don't open a public
issue for it. You'll get an answer within a week; a fix goes out as a new release, with credit if
you want it.

Only the latest release is supported.

## What CalcSuite does and doesn't do

- **No telemetry.** CalcSuite sends nothing about you or your calculators anywhere.
- **It goes online only when you ask:** TI's website (to see whether a newer calculator OS
  exists), ticalc.org and GitHub (programs you choose under Get programs), PyPI (ffmpeg, when
  you first record a video), and the emulators' own download pages (Make a PC copy).
- **Admin rights only for the USB driver**, once per calculator: CalcSuite shows exactly what
  will change first, and Windows asks.
- **Nothing is installed.** It runs from the folder you unzipped; everything it saves stays in
  that folder's `CalcSuite files`. Deleting the folder removes it.
- **Your calculator's ROM** (for the PC copy) stays on your PC and is never uploaded.

## Checking a download

Each release lists the zip's SHA-256 in `SHA256SUMS.txt`, and from 1.0.2 on carries build
provenance: GitHub signs that the zip was built by this repository's release workflow from the
tagged commit, not on anyone's PC. Check it with the GitHub CLI:

    gh attestation verify CalcSuite-<version>-win64.zip -R paul-kratky/CalcSuite

The same signed provenance is also a release file, `<zip>.intoto.jsonl` (and
`<zip>.sigstore.json`), for SLSA tools.

The releases before 1.0.2 (back to 0.1.0) carry a `.sig` beside each file instead: the owner's
SSH signature, added on 2026-11-28 after checking each file against its `SHA256SUMS.txt` (0.1.0
and 0.2.0 had none). The public key is in `.github/allowed_signers`. Check a file with:

    ssh-keygen -Y verify -f allowed_signers -I 199176229+paul-kratky@users.noreply.github.com -n file -s <file>.sig < <file>

Release tags and commits are signed (GitHub shows them as Verified). The source of every part
of the zip is in this repository; `.github/workflows/release.yml` is the exact build.
