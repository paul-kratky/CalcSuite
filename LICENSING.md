# Licensing

CalcSuite is MIT-licensed ([LICENSE](LICENSE)): everything in this repository, except the parts
below, which keep their own licences.

| Part | Licence | Why |
| --- | --- | --- |
| `tools/nspire_cli/` and `nspire-cli.exe` | GPL-3.0-or-later | It links libnspire ([tools/nspire_cli/COPYING](tools/nspire_cli/COPYING)) |
| `tools/ti84_cli/` and `ti84-cli.exe` / `ti89-cli.exe` | GPL-3.0-or-later | It follows TILP's link protocol code |
| `tools/driver_helper/` and `calcsuite-driver.exe` | LGPL-3.0-or-later | It links libwdi statically |
| `tools/tns_writer.py` | MPL-1.1 | A port of Luna's .tns writer |
| `tools/third_party_py/tivars` | MIT | TI-Toolkit's tivars |
| `tools/rom_dumpers/` | GPL (see its README) | CEmu's and TILP's ROM dumpers, sent to the calculator as files |
| `third_party/` | each project's own ([third_party/README.md](third_party/README.md)) | Luna MPL-1.1, libnspire GPL-3.0-or-later, libwdi LGPL-3.0-or-later, libusb LGPL-2.1-or-later |

The link tools and the driver helper run as their own programs; CalcSuite's MIT code talks to
them over their command line. Every part's source is in this repository; the release zip's
`Licences` folder carries the texts.

Programs from **Get programs** keep their authors' licences: CalcSuite links to them and
downloads them only when you ask.
