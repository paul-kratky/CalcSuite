# CalcSuite "Get programs": curated library (draft, 2026-11-27)

Who it's for: an engineering student (computer engineering) who uses the calculators for real work.
Games are left out.
Machine-readable copy: `program_library.json` (same folder). It has 46 entries: 42 community items and 4 official TI-84 CE apps. The remaining official apps are in the tables below.

How the research was done: I read the ticalc.org directory listings and fileinfo pages, GitHub repositories, education.ti.com detail pages and the KhiCAS author's site, all on 2026-11-27.
Cemetech and TI-Planet both block Anthropic's crawlers (ClaudeBot, Claude-Web, anthropic-ai) in robots.txt. I respected that: I read only their robots.txt and took their details from search snippets.
"verified" in the JSON means I opened the item's own fileinfo or release page. Items marked unverified come from a directory listing (title, size, date, description), and their author and inner file names still need checking.

Legend: **ASM** = native code. On the CE it runs on OS 5.4.0 directly; on OS 5.5 and later it needs arTIfiCE plus a shell.

---

## 1. TI-84 Plus CE (OS 5.4.0, non-Python)

OS 5.4.0 still runs ASM and C programs, so Cesium, clibs, KhiCAS and the C tools all work. **CalcSuite must never offer an OS update to this user.** TI's current bundle is OS 5.8.5, which removes ASM, and the CE can't be downgraded.

| # | Item | What it does for you | Cat. | Source / info | Direct download | Inside the zip | Size | Author | Licence | Year | Popularity | OS notes | Conf. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Cesium 3.8.0** | Shell: run any program (archived or not), hide, lock and rename | Shell | ticalc [fileinfo 465/46574](https://www.ticalc.org/archives/files/fileinfo/465/46574.html); GitHub mateoconlechuga/cesium | `https://www.ticalc.org/pub/84plusce/asm/shells/cesium.zip` (alt: GitHub release v3.8.0 `cesium.zip`) | `cesium_english.zx0.8xp` (+ dutch/french/italian/turkish) | 70 KB | MateoConLechuga | not stated | 2026 | 22,119 dl; **9.42**, #5 top-rated | ASM; 5.4.0 ok | High |
| 2 | **CE C Libraries (clibs) v15.0** | Runtime libraries most C programs need (install once) | Dependency | [GitHub releases](https://github.com/CE-Programming/libraries/releases/latest) | `https://github.com/CE-Programming/libraries/releases/download/v15.0/clibs.8xg` | n/a (.8xg) | small | CE-Programming | not shown on release page | v15.0 | standard dependency | any OS | High |
| 3 | **KhiCAS (χCAS)** | Full computer algebra system (Giac/Xcas) inside the CE | CAS | [Parisse's page](https://xcas.univ-grenoble-alpes.fr/backup/ti/khicas84.html) | `https://www-fourier.univ-grenoble-alpes.fr/~parisse/ti/khicas84.zip` or `.../khicas84.b84`; nightly builds on GitHub KhiCAS/ti-ce | INST + artifice2 + app files | about 3 MB of archive | Bernard Parisse | **GPL2** (INST closed, free for non-commercial use) | 2024 | flagship port | below 5.5 you run INST directly, so 5.4.0 is in range; never upgrade the OS | Med-high |
| 4 | **Converty** | 98-unit converter in 12 groups | Units | ticalc [479/47911](https://www.ticalc.org/archives/files/fileinfo/479/47911.html) | `https://www.ticalc.org/pub/84pluscse/basic/science/converty.zip` | `CONVERTY.8xp` | 71 KB zip / 3 KB | TICalc Arts | not stated | 2024 | 1,789 dl | BASIC | High |
| 5 | **Programmer's Calculator v1.21** | RPN hex/dec/oct/bin calculator with bitwise operations | CompE | ticalc [476/47654](https://www.ticalc.org/archives/files/fileinfo/476/47654.html) | `https://www.ticalc.org/pub/84plusce/asm/math/progcalc.zip` | `PROGCALC.8xp`, `DrMono.8xv`, `DrSans.8xv` | 159 KB | Ander D'nar | LICENSE in zip | 2021 | 1,680 dl | ASM/C (+clibs likely) | High |
| 6 | **LOGiCE** | Boolean minimiser (Quine-McCluskey, 10 variables), truth tables, K-maps | CompE | ticalc [480/48002](https://www.ticalc.org/archives/files/fileinfo/480/48002.html); GitHub atomicra1n/LOGiCE | `https://www.ticalc.org/pub/84plusce/asm/math/logice.zip` | `bin/LOGiCE.8xp` | 125 KB / 12 KB | Megami Tensei | **MIT** | 2026 | 554 dl | C; **needs clibs** | High |
| 7 | Graph3CE v2.0 | 3D surface graphing (6 functions, rotate, trace) | Graphing | [ticalc asm/math](https://www.ticalc.org/pub/84plusce/asm/math/) | `https://www.ticalc.org/pub/84plusce/asm/math/graph3cev2.0.zip` | .8xp (name not checked) | 31 KB | Casio Prizm port | not stated | 2025 | not checked | ASM, beta | Med |
| 8 | Complex Math | Complex arithmetic in rectangular and polar form (phasors) | Complex | [ticalc basic/math](https://www.ticalc.org/pub/84pluscse/basic/math/) | `.../84pluscse/basic/math/complexmath.zip` | .8xp | 190 KB | not checked | not stated | 2019 | not checked | BASIC | Med |
| 9 | Resistor Color Code | Colour bands to value and back, 3 to 6 bands | Electronics | ticalc [455/45501](https://www.ticalc.org/archives/files/fileinfo/455/45501.html) | `.../84pluscse/basic/science/resistorcolorcode.zip` | `RESISTOR CSE.8xp`, `θR.8xp` | 3 KB | Osias Hernandez | not stated | 2013 | 2,916 dl | BASIC (written for CSE) | Med-high |
| 10 | Ohm's Law Calculator | V, I, R, P and X from any two values | Electronics | [ticalc basic/science](https://www.ticalc.org/pub/84pluscse/basic/science/) | `.../ohmslaw.zip` | .8xp | 1 KB | not checked | not stated | 2021 | not checked | BASIC | Med |
| 11 | 555 Astable Multivibrator | 555 timer design: frequency and duty cycle | Electronics | same folder | `.../555plusc.zip` | .8xp | 4 KB | not checked | not stated | 2014 | not checked | BASIC | Med |
| 12 | Capacitor Value Finder | Decodes "104"-style capacitor codes | Electronics | same folder | `.../discap.zip` | .8xp | 1 KB | not checked | not stated | 2020 | not checked | BASIC | Med |
| 13 | Cross-Section Properties v1.03 | Area, centroid, I, and stresses for polygon sections | Mech. of materials | same folder | `.../polygon84.zip` | .8xp | 372 KB | not checked | not stated | 2017 | not checked | BASIC | Med |
| 14 | CEdit | Text editor for notes and formula sheets (AppVars) | Notes | [ticalc asm/programs](https://www.ticalc.org/pub/84plusce/asm/programs/) | `https://www.ticalc.org/pub/84plusce/asm/programs/cedit.zip` | .8xp | 2.2 MB zip | not checked | not stated | 2021 | not checked | ASM | Med |

Other good items in the same folders: ALLSOLVE2 (real roots and extrema), Integral (fnInt plus Simpson), Bessel functions, INTRPOL8 (interpolation), BaseConv 1.2, Binary Operations, Centroid Calculator, Moments Calculator, Forced Vibrations, and Celtic CE (a BASIC library, needs ASM).

### Official TI-84 Plus CE apps

| App | Version | File | Size | Direct URL (`https://education.ti.com` + path) | Notes |
|---|---|---|---|---|---|
| **Science Tools** | 5.6 | `SciTools_CE_5.6.0.0029.8ek` | 50 KB | `/download/en/ed-tech/DB947BF05FB2414081C2B4DAA47271D1/18E2A49485724C1389FDA5F4DE0F1E4D/SciTools_CE_5.6.0.0029.8ek` | Units, significant figures, vectors. Built after OS 5.6, so 5.4.0 not confirmed |
| **PlySmlt2** (poly roots + simultaneous equations) | 5.5 | `PlySmlt2_CE_5.5.0.0038.8ek` | 86 KB | `/download/en/ed-tech/07D95F33132D4B46B0B7BACF09E10E9C/DE770601919446F68A847597CC98DD5C/PlySmlt2_CE_5.5.0.0038.8ek` | Best engineering app TI makes for the CE |
| Periodic Table | 5.5 | `Periodic_CE_5.5.0.0038.8ek` | 45 KB | `/download/en/ed-tech/BDE2DB7E54964A4CBAB6D8611239FAB2/11C5FAEDFDF548DD8C98D76D9D799C35/Periodic_CE_5.5.0.0038.8ek` | |
| CellSheet | 5.1.1 | `CelSheet_CE_5.1.1.0017.8ek` | 120 KB | `/download/en/ed-tech/EA94E71DFFD94CB0A8AB73EF0A58B9D4/1F387F1A3A454B93B98A039EEE0319CA/CelSheet_CE_5.1.1.0017.8ek` | |
| Conic Graphing, Inequality Graphing, Probability Simulation, Transformation Graphing, SmartPad CE, Cabri Jr (5.8.3), TI-Innovator Hub, Vernier EasyData, Language Localization | various | see [TI search](https://education.ti.com/en/software/search/ti-84-plus-ce) | | detail pages listed there | Low value for engineering; Cabri Jr 5.8.3 is the newest and may assume a newer OS |
| ~~OS and Apps Bundle 5.8.5 / OS 5.8.5~~ | | | | | **Never offer to a 5.4.0 user** |

**Licence handling (all TI downloads):** no login is needed. Each page has a licence link and says *"By downloading the application you indicate your agreement with the terms and conditions of the License."* That is implied acceptance. The licence allows installing on a TI calculator plus one backup copy, and forbids reverse-engineering, resale and use on non-TI emulators. So CalcSuite should **show the licence and require an "I accept" click, or open the TI page in the browser**. It should not silently auto-download, and must never mirror or cache the files for other users. Most of these apps are preloaded on CE calculators anyway: check the calculator's app list first.

---

## 2. TI-89 Titanium (AMS 3.10)

AMS 3.10 is the latest Titanium OS, so nothing needs updating. Every pick below is TI-BASIC (.89p/.89f/.89g) or a Flash app (.89k), so **no kernel is needed**. If you add ASM programs later, many need PreOS or KerNO plus HW3Patch on the Titanium.

| # | Item | What it does | Cat. | Info | Direct download | Calculator files | Size | Author | Licence | Year | Popularity | Conf. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Laplace and Z transform (LZT)** | Forward and inverse Laplace and Z transforms, circuit and block-diagram simulation | Signals | [296/29629](https://www.ticalc.org/archives/files/fileinfo/296/29629.html) | `https://www.ticalc.org/pub/89/basic/math/calculus/lzt.zip` | `lztR7.89g` (+helpers per PDF) | 440 KB | Jiri Bazant | not stated | 2014 | **about 120,788 dl (#46 all-time)**, 8.68 | High |
| 2 | **Control System Toolbox r1.3** | Bode, Nyquist, root locus, step response, margins, PID and lead/lag design | Control | [379/37951](https://www.ticalc.org/archives/files/fileinfo/379/37951.html) | `https://www.ticalc.org/pub/89/basic/science/electricity/cst.zip` | about 70 files in `cst-1.3.89g/`; run `install()` | 268 KB | Loreto Parisi | not stated | 2005 | **51,023 dl**, 8.45 | Med-high |
| 3 | **FluidTI (IAPWS-IF97)** | Steam and water property tables on the calculator | Thermo/fluids | [282/28270](https://www.ticalc.org/archives/files/fileinfo/282/28270.html) | `https://www.ticalc.org/pub/89/basic/science/applied/fluidti_if97_eng.zip` | the `.89g` file (skip .92G/.9Xg) | 659 KB | Krause, Kretzschmar | not stated | 2003 | 21,931 dl, 8.38 | Med-high |
| 4 | **Logical Suite v1.34** | K-map editor and simplifier, gate drawing, counter design | CompE | [370/37085](https://www.ticalc.org/archives/files/fileinfo/370/37085.html) | `https://www.ticalc.org/pub/89/basic/science/electricity/karnaugh.zip` | `TI89/logic.*.89p/.89m` | 119 KB | Thiernesse Vincent | not stated | 2006 | 16,990 dl | High |
| 5 | **Table of Elements v1.2 (EN)** | Periodic table app with 14 sort orders | Reference | [269/26904](https://www.ticalc.org/archives/files/fileinfo/269/26904.html) | `https://www.ticalc.org/pub/89/flash/periodicenglish1.2.zip` | `PeriodE.89k` | 91 KB | Eric Marion, Jake Poznanski | not stated | 2003 | 34,171 dl | Med (pre-Titanium app) |
| 6 | **BE (Basic Extensions)** | 175+ maths, EE and DSP functions for BASIC | Math library | [464/46405](https://www.ticalc.org/archives/files/fileinfo/464/46405.html) | `https://www.ticalc.org/pub/89/flash/be.zip` | `BE/BE.89k` (+PDF manual) | 1.06 MB | Ralph Schenn | not stated | **2026** | 5,898 dl, active | Med-high |
| 7 | Statics 2D / 3D | 2D and 3D equilibrium and trusses, 9x9 systems | Statics | [applied/](https://www.ticalc.org/pub/89/basic/science/applied/) | `.../applied/statics2.zip`, `.../applied/statics3.zip` | .89p | 235 / 257 KB | not checked | not stated | 2008 | not checked | Med |
| 8 | Resistencia de Materiales v2.01 | Stresses, Mohr's circle (EN/ES) | Mech. of materials | same | `.../applied/rm_v_201.zip` | .89p | 18 KB | not checked | not stated | 2005 | rating 8.70 | Med |
| 9 | Numerica v1.0 | Roots, interpolation, integration, Euler/RK ODEs | Numerical | [calculus/](https://www.ticalc.org/pub/89/basic/math/calculus/) | `.../calculus/numerica.zip` | .89p | 25 KB | not checked | not stated | 2003 | rating 7.46 | Med |
| 10 | Ecuacion | About 900-equation database plus solver and ODEs | Formula reference | applied/ | `.../applied/ecuacion.zip` | .89p/.89g | 786 KB | not checked | not stated | 2007 | 28,136 dl | Med |
| 11 | Multiloop DC and AC Circuits | Mesh analysis for DC and AC | Circuits | [electricity/](https://www.ticalc.org/pub/89/basic/science/electricity/) | `.../electricity/crcuits.zip` | .89p | 64 KB | not checked | not stated | 2007 | not checked | Med |
| 12 | tlines89 v1.1 | Transmission lines, Smith chart, stub matching | RF | electricity/ | `.../electricity/tlines.zip` | .89p | 5 KB | not checked | not stated | 2002 | not checked | Med |
| 13 | Chemistry v1.00 (Flash) | Periodic and solubility tables, thermo data, molar mass | Reference | [flash/](https://www.ticalc.org/pub/89/flash/) | `https://www.ticalc.org/pub/89/flash/chemistry.zip` | .89k | 80 KB | not checked | not stated | 2003 | not checked | Med-low |

Other strong items in `/pub/89/basic/science/electricity/`: TiSpice v4.11 (symbolic circuit simulator), Signal Processing v240, FFT 128/64, LED Calculator, Microstrip calculator, Logic Designer 2.1.1, Routh-Hurwitz (in applied/), and Gear (AGMA).
For thermodynamics: Termo2 (IAPWS-IF97 plus ideal gas, rated 8.33). For structures: Vigas beam solver, BeamXP/FrameXP/TrussXP.

### Official TI-89 Titanium apps

Each is a direct download with no login and the same implied-acceptance licence as the CE apps, so use a licence gate. The URL is `https://education.ti.com` + path.

| App | Ver. | File | Size | Path / page | Notes |
|---|---|---|---|---|---|
| **Calculus Tools** | 1.00 | `calctool.89k` | 54 KB | `/download/en/ed-tech/BD230769676A4CC0A42AFB247D22343D/4544A8D391A64225BE124C107BA84447/calctool.89k` | Fourier series, vector calculus, numerical integration comparisons |
| **Polynomial Root Finder** | 1.00 | `tipolyrt.89k` | 49 KB | `/download/en/ed-tech/0FE5BAA252FD4BB7BD6B12AB8B1763D6/10BDE04615FC41D7BDAD58C7423AFE2C/tipolyrt.89k` | |
| **Simultaneous Equation Solver** | 1.00 | `tismlteq.89k` | 84 KB | `/download/en/ed-tech/BD358C4836B84DBCBA254D6554FBBEAC/120EA68042BF45629444CEED5336286C/tismlteq.89k` | |
| **Statistics with List Editor** | 1.03 | `tistatle.89k` | 309 KB | `/download/en/ed-tech/31FC737C43CF43B0ADA1CF67420C3AA8/6DF4857BC4F44177A2BBBFAB9FDDF616/tistatle.89k` | |
| CellSheet | 1.20 | `ticsheet.89k` | 151 KB | `/download/en/ed-tech/C348D29C99284143B9E3FE93CF6742A6/13103EB2C0E2483CB9FB0A8143B5A620/ticsheet.89k` | |
| NoteFolio | 1.00 | `tinotes.89k` | 21 KB | `/download/en/ed-tech/9049401117DA4AB69EC0913806887C0E/68D94E66EBC445C1AAA1D1E00A2FDCB9/tinotes.89k` | Notes app (NoteFolio Creator .exe is Windows-only) |
| Symbolic Math Guide | 2.00 | `smg200.89k` | 280 KB | `/download/en/ed-tech/7E54DC888F25499A8FEE6B5C4802BFC3/2DC61AF1BA454E609A12AB5877E4C029/smg200.89k` | Step-by-step algebra |
| Organizer (Calendar/Contacts/Planner/Tasks) | 1.0x | `ticalndr/ticntcts/tiplannr/titasks.89k` | 36-98 KB | see the [Organizer page](https://education.ti.com/en/software/details/en/B923170F673847198159A50A990A142F/89organizer) | 4 separate apps |
| Finance 1.11, CalcuFin, Cabri Geometry 2.05, Geometer's Sketchpad 1.04, StudyCards, Equation Writer | | | | [TI search](https://education.ti.com/en/software/search/ti-89-ti-89-titanium) | Lower value |
| **EE\*Pro 1.10 / ME\*Pro 1.01** | | | | [EE\*Pro page](https://education.ti.com/en/software/details/en/B89A02AE62DC40D7870EE9B6370A1865/89eepro), [ME\*Pro page](https://education.ti.com/en/software/details/en/B393BC134B2541D1B51DD7C21C549928/89mepro) | **Request form (name, email, country); the link arrives by email. Cannot be automated: send the user to the page.** EE\*Pro is usually preloaded on the Titanium already. |

---

## 3. TI-Nspire CX II CAS (OS 6.4.0.74)

6.4.0.74 is TI's current CX II CAS OS (`TI-NspireCXIICAS-6.4.0.74.tcc2`), so no update is needed. Everything below is a plain .tns file (TI-Basic or Lua) and **none needs Ndless**. Built-in Python covers scripting. Library files must go to **/MyLib**, and the user then runs *Refresh Libraries* or restarts the handheld.

| # | Item | What it does | Cat. | Info | Direct download | Files | Size | Author | Licence | Year | Popularity | Conf. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **FormulaPro 1.42b** | EE equation solver: 700+ equations, 16 categories, units, reference (EE\*Pro for Nspire) | EE | [GitHub adriweb/EEPro-for-Nspire](https://github.com/adriweb/EEPro-for-Nspire); [TI activity](https://education.ti.com/en/activity/detail/formulapro); ticalc [450/45028](https://www.ticalc.org/archives/files/fileinfo/450/45028.html) | `https://github.com/adriweb/EEPro-for-Nspire/raw/master/FormulaPro.tns` (bare .tns). Alt: TI `https://education.ti.com/-/media/8F382C3A46184F9BA0EA386497561661` | `FormulaPro.tns` | about 1.8 MB zip on ticalc | Jim Bauwens, Adriweb | **LGPL-3** | 2013 (repo archived 2022) | 10,595 dl; hosted by TI | High |
| 2 | **Math Equations Library 4.0 (CAS)** | Searchable formula sheets: calculus I-III, linear algebra, ODEs, statistics, vectors | Formula reference | [460/46022](https://www.ticalc.org/archives/files/fileinfo/460/46022.html) | `https://www.ticalc.org/pub/nspire/basic/math/mathlibrary.zip` | `MyLib/*.tns` + `Workspaces/*` | 3.0 MB | Rachel Bush | not stated | 2021 | **48,416 dl (#183)**, #7 this week | High |
| 3 | **Chemistry Library** | `balance("H2+O2=H2O")`, `mass("H2SO4")`, element lookup | Chemistry | [417/41715](https://www.ticalc.org/archives/files/fileinfo/417/41715.html) | `https://www.ticalc.org/pub/nspire/basic/science/chemistry.zip` | `Chemistry_EN.tns` -> MyLib | 28 KB | Nelson Sousa | not stated | 2009 | 47,886 dl | High |
| 4 | **Multilingual Periodic Table** | Full element data, 3D crystal structures | Reference | [444/44465](https://www.ticalc.org/archives/files/fileinfo/444/44465.html) | `https://www.ticalc.org/pub/nspire/lua/science/periodicanimated.zip` | `multiperiodic.tns` | 23 KB .tns | Nick Steen | not stated | 2014 | 33,264 dl, **8.61** | High |
| 5 | **bodeplot v2.1.1** | Bode gain and phase plots from a transfer function | Control | [452/45272](https://www.ticalc.org/archives/files/fileinfo/452/45272.html) | `https://www.ticalc.org/pub/nspire/lua/math/bode.zip` | `bode.tns` | 5 KB | najiji | not stated | 2014 | 11,246 dl | Med-high |
| 6 | Electrical Engineering Tools | DSP, RLC, power and EM documents | EE | [478/47870](https://www.ticalc.org/archives/files/fileinfo/478/47870.html) | `https://www.ticalc.org/pub/nspire/basic/science/ticalcversion1.1.zip` | `DSP/RLC/Power/EM_Interactions.tns` | 27 KB | Asil Poyraz Yongaci | LICENSE in zip | 2023 | 886 dl | Med |
| 7 | Runge-Kutta v2.05 | ODE systems (1st and 2nd order) with plots | Numerical | [basic/math/](https://www.ticalc.org/pub/nspire/basic/math/) | `.../basic/math/rungekutta4.zip` | .tns | 25 KB | not checked | not stated | 2017 | not checked | Med-high |
| 8 | Number Base Converter | bin/oct/dec/hex including fractions | CompE | [lua/math/](https://www.ticalc.org/pub/nspire/lua/math/) | `.../lua/math/numberbaseconverter.zip` | .tns | 6 KB | not checked | not stated | 2019 | not checked | Med-high |
| 9 | Laguerre | Up to 9 complex polynomial roots | Polynomials | lua/math/ | `.../lua/math/laguerre.zip` | .tns | 8 KB | not checked | not stated | 2019 | not checked | Med |
| 10 | Truss 2-D and 3-D v1.01 | Member and reaction forces | Statics | [basic/science/](https://www.ticalc.org/pub/nspire/basic/science/) | `.../basic/science/threedtruss.zip` | .tns | 194 KB | not checked | not stated | 2019 | not checked | Med |
| 11 | Cross-Section Properties v2.0 | Section properties and combined stresses | Mech. of materials | basic/science/ | `.../basic/science/polygon.zip` | .tns | 360 KB | not checked | not stated | 2017 | not checked | Med |
| 12 | Two Port Network Solver (CAS) | Z/Y/h/ABCD conversion, series/parallel/cascade | Circuits | basic/science/ | `.../basic/science/tpn_cas.zip` | .tns | 18 KB | not checked | not stated | 2015 | not checked | Med |
| 13 | Complex Analysis Functions | Poles, residues, contour integrals, Laplace | Complex/transforms | basic/math/ | `.../basic/math/cmplxanlys.zip` | .tns (MyLib) | 6 KB | not checked | not stated | 2013 | not checked | Med |
| 14 | Advanced Regression (CAS) | Nonlinear regression with ANOVA and standard errors | Statistics | basic/math/ | `.../basic/math/advreg.zip` | .tns | 33 KB | not checked | not stated | 2014 | not checked | Med |
| 15 | Darcy-Weisbach Application | Friction factor, head loss, Reynolds number | Fluids | basic/science/ | `.../basic/science/darcyweisbach.zip` | .tns | 519 KB | not checked | not stated | 2019 | not checked | Med |

Also worth a look: Physics Formulas and Workspace 2.1, Beam Shear-Moment Diagram, Mohr's Circle v2.00, Bernoulli Energy Equation, Hazen-Williams, Manning's, Dew Point, Advanced Interpolation (Lua), Jordan Normal Form (Lua), Total Resistance (Lua), and Truss (Lua, draw the truss).

### Official TI for the Nspire CX II CAS

TI has no add-on "apps" for the Nspire. The things it does offer:

- **OS 6.4.0.74**: already installed. Same implied-acceptance licence, plus *"Users under 18 need parent/guardian consent"*.
- **Built-in libraries** (linalgcas, numtheory and others) ship with the OS and software. If one is deleted, reinstalling the OS restores it.
- **TI activities** (`education.ti.com/en/activity/detail/...`) are direct `-/media/<GUID>` .tns links with no licence gate. FormulaPro is one of them.

---

## 4. Items that need special handling

| Item | Why | What CalcSuite should do |
|---|---|---|
| KhiCAS (CE) | Needs about 3 MB of free archive; multi-file; on-calc INST step; the OS must match | Wizard: check ARC FREE, prompt for backup and purge, send all files, tell the user to run INST, then clean up the install AppVars. Never offer an OS update. |
| Cesium, ProgCalc, LOGiCE, Graph3CE, CEdit (CE) | ASM/C | Fine on 5.4.0. Read the OS version over USB; if it's 5.5 or later, warn that arTIfiCE is needed. Install clibs automatically when it's a dependency. |
| Control System Toolbox (89) | About 70 variables in one folder; install() step; bundled KerNO/HW3Patch | Keep folder names from the variable headers; skip `tools/`, `.DS_Store` and the PDF unless asked. |
| LZT, FluidTI (89) | Large .89g groups | Check free RAM/archive first. Filter files by extension (.89*). |
| Flash apps (.89k: Table of Elements, BE, Chemistry; all TI 89 apps) | Flash-app transfer protocol; pre-Titanium apps are not guaranteed | Use app-send code; treat a failure as "incompatible", not "corrupt". |
| Math Equations Library, Chemistry Library, Complex Analysis (Nspire) | Library documents | Put them in `/MyLib`, then tell the user to Refresh Libraries. |
| All TI official downloads | Implied-acceptance licence; no redistribution | Show the licence and get an explicit accept, or open the page in the browser. Download from TI on each request; don't mirror. |
| EE\*Pro / ME\*Pro (89) | Email request form | Link out only. |
| CE OS / Apps Bundle 5.8.5 | Removes ASM; can't downgrade | Hard-block for a 5.4.0 calculator. |
| Resistor Color Code (CE) | Program name contains the θ token | Use the name from the .8xp header, not the filename. |
| Zips with docs, sources and screenshots | Mixed content | Send only `.8x*` / `.89*` / `.tns`, choosing the right model's files where a zip holds several. |
| GitHub "latest" items (clibs, Cesium, LOGiCE) | Versions change | Resolve through the GitHub Releases API (`/repos/{o}/{r}/releases/latest`) and cache by ETag. |

---

## 5. Source etiquette and terms

**ticalc.org**
- robots.txt (`User-agent: *`) disallows only `/cgi-bin`, `/includes`, `/pub/text/logs` and one old text file. **`/pub/` (the file archive) and `/archives/` are open.**
- I found no terms against linking to or downloading single files. The site policies cover content only (no ROMs, no copyright violations) and themselves point people to download links. Footer: "Copyright © 1996-2012, the ticalc.org project. All rights reserved." The old FTP bulk-download service was shut down over security problems and abuse.
- Verdict: **a client downloading one file when the user clicks is fine.** It is no different from a browser download.

**Cemetech**
- robots.txt blocks 22 named data-harvesting/AI bots (GPTBot, ClaudeBot, Bytespider, ...) from the whole site; everything else is allowed. There is a sitemap at `/sitemap.xml`.
- No documented API was found. I didn't read their ToS, because the site blocks Anthropic's crawlers.
- Verdict: a user-triggered single download with an honest client User-Agent probably fits the spirit, but this is unverified. **Prefer ticalc or GitHub copies** (most Cemetech CE items are mirrored, e.g. Cesium and Converty). Otherwise open the Cemetech page in the browser, or ask the admins (Cemetech is friendly to tool authors).

**TI-Planet**
- robots.txt: `User-agent: *` Allow `/` with `Content-Signal: search=yes, ai-train=no, use=reference`. It blocks many AI bots outright and reserves rights under EU DSM Art. 4. Sitemap at `/sitemap.xml`.
- No public API was found.
- Verdict: the same as Cemetech. A user-click download is not AI training, but to be safe prefer GitHub or ticalc mirrors, or link out to the archive page.

**education.ti.com**: direct file URLs with no login, but implied-acceptance licences (see above). Link out or gate behind an explicit accept, and never mirror.

**Recommended etiquette for CalcSuite:**
1. Download only on an explicit user click. No prefetching, no crawling, no "download all".
2. Send an identifying User-Agent, e.g. `CalcSuite/1.0 (+https://github.com/paul-kratky/CalcSuite)`. Don't impersonate a browser.
3. Cache each file locally and send `If-Modified-Since`/`ETag` on refresh. Never re-download for every send.
4. Ship the curated catalogue inside the app or as a JSON file in the CalcSuite repo, rather than scraping listings at runtime. If you refresh metadata, do it at most once a day.
5. Link the original fileinfo or author page next to every item, for credit and readme/licence text. Show the author's name.
6. Don't rehost third-party files in CalcSuite releases unless the licence allows it (MIT/LGPL/GPL items may be redistributed; "not stated" items and TI files may not). Pointing at the original URL avoids the question.
7. Handle 404s gracefully, since files get replaced. Fall back to opening the info page.

---

## 6. Machine-readable indexes

- **ticalc.org `https://www.ticalc.org/pub/master.index`**: plain text, about 1.9 MB, the whole archive. Each section starts `Index of /pub/<path> (<description>)`, followed by lines of `<filename> <title>`. No sizes, dates or IDs, and no fileinfo IDs. It's good for an offline search index: fetch it rarely and cache it.
- **ticalc.org RSS 2.0** (from [/services/syndication.html](https://www.ticalc.org/services/syndication.html)): `/rss/files.rss` (new or updated files over the last 3 days, refreshed every 6 h, 50 KB or more), `/rss/featured.rss`, `/rss/reviews.rss`, `/rss/news.rss`, and `/rss/headlines.rss` (RSS 1.0). Useful for a "new in archive" feed.
- **ticalc.org directory pages** (`/pub/<model>/<lang>/<category>/`) are stable HTML tables with filename, title, size and date. Fileinfo pages (`/archives/files/fileinfo/NNN/NNNNN.html`) carry author, exact bytes, download counts, rating and zip contents. **Don't scrape them at runtime.**
- **Cemetech**: only `sitemap.xml`; no API found.
- **TI-Planet**: only `sitemap.xml`; no documented API found.
- **GitHub**: the REST Releases API (unauthenticated, 60 requests/h per IP) for clibs, Cesium, LOGiCE and the KhiCAS nightly builds.
- **TI**: no API. Detail pages are `/en/software/details/en/<GUID>/<slug>` and files are `/download/en/ed-tech/<GUID>/<GUID>/<file>`. The GUIDs have been stable for years, but treat them as able to change.
