# 3D animatsiyali taqdimotlar — kuchaytirish rejasi (4/10 → 9+/10)

Sana: 2026-10-16. Qamrov: **🫀 3D Anatomiya** (`services/med3d`, haqiqiy `.glb` modellar) — asosiy;
**🧊 3D Pro** (`services/pro3d`, fonsiz rasmlar) — 8-bo'limda.
Oldingi reja va texnik tarix: `docs/tibbiyot_3d_reja.md`.

> **0-bosqich bajarildi.** #212 birlashtirishda PR ichidagi "Eski branch tarixi" commiti eski daraxtni saqlab
> qolgan va `main` #207 holatiga qaytgan edi: 3D Anatomiya (#208, #209, #211), saytdagi bepul sinov rasmlari
> (#210), Jurnal matni va "Orqaga" tugmasi (#211) yo'qolgan edi. Shu shoxda hammasi tiklandi, #212 ning o'z
> o'zgarishi (oddiy taqdimotda 4-5 rasm) saqlandi, testlar o'tdi. **Bu shox `main` ga qo'shilmaguncha botda
> 3D Anatomiya yo'q.**

---

## 1. Nega hozir 4/10 — halol tashxis

Poydevor kuchli (haqiqiy 3D, bitta GLB'da to'g'ri chuqurlik, umumiy soya, lotincha nomlar, joyida almashish).
Lekin tomoshabin ko'radigan narsa — dizayn, harakat, a'zoni ochib berish — bir xil va sayoz.

| Yo'nalish | Hozir nima bor | Muammo | Ball |
|---|---|---|---|
| Dizayn | Bitta uslub: to'q ko'k fon, moviy yorliq. Har slayd: chapda matn, o'ngda model | 15 slaydda bir xil kompozitsiya — 3-slayddan keyin zerikarli | 3 |
| Harakat | AI burchak beradi, kod ≤45° ga silliqlaydi. Ketish doim "yuqoriga", kelish "pastdan". Morph hamma joyda 2.2 s | Har o'tish bir xil "biroz burilish + uchib ketish". Ritm yo'q, kulminatsiya yo'q | 4 |
| A'zoni ko'rsatish | Yorliq faqat butun organga. Yaqinlashish ≤1.6x | Organ ichidagi qismlar (bo'lmacha/qorincha, bo'laklar, bo'limlar) nomlanmaydi. Kesim, qatlam ochish, ajratish (explode), funksiya (qon/havo/ovqat yo'li) yo'q | 4 |
| Matn | Har slaydda 2-4 gap, bir xil tuzilish | Faktlar AI xotirasidan, tekshirilgan manba yo'q. "Bilasizmi?", viktorina, raqam kartasi yo'q | 5 |
| Texnik poydevor | GLB yozuvchi, AO soya, kamera proyeksiyasi, hajm nazorati | Yaxshi | 7 |
| Ko'rish va moslik | Zaxira rasm — 1×1 bo'sh PNG | Telefonda, WPS, Google Slides, Keynote'da slayd **bo'sh**. Telegram'da ko'rib bo'lmaydi | 2 |
| Sifat nazorati | Morph simulyatori qo'lda ishlatilgan (repoda yo'q) | Avtomatik vizual tekshiruv yo'q, PowerPoint'da hali tekshirilmagan | 2 |

O'rtacha ≈ 3.9 — siz bergan 4 ball bilan mos.

**Asosiy sabab:** hamma qaror (burchak, kim chiqib ketadi, nima nomlanadi) bitta AI so'roviga yuklangan, kodda esa
faqat bitta "uslub" va bitta "harakat" bor. AI har safar o'xshash JSON beradi → taqdimotlar bir-biriga o'xshaydi.

---

## 2. "10/10" nimani anglatadi — o'lchanadigan mezonlar

Har taqdimot avtomatik baholanadi (7.3-bo'lim). Maqsad — har yo'nalishda ≥ 8.5.

| Yo'nalish | O'lchov (avtomatik) | Maqsad |
|---|---|---|
| Dizayn | Kompozitsiyalar xilma-xilligi; ketma-ket takror yo'q; matn kontrasti ≥ 4.5:1; matn qutidan chiqmaydi | ≥ 5 xil kompozitsiya / 10 slayd |
| Harakat | Takrorlanmaslik indeksi = noyob harakat imzolari / o'tishlar | ≥ 0.9; ≥ 6 xil harakat turi / 10 slayd |
| A'zoni ko'rsatish | Organ ichidagi nomlangan joylar soni; kesim/qatlam/oqim sahnalari bormi | ≥ 12 nomlangan joy; ≥ 2 "maxsus" sahna |
| Aniqlik | Faktlar skill kartasidagi tekshirilgan ro'yxatdan; o'zbekcha + lotincha atama lug'atdan | 100% |
| Moslik | Haqiqiy zaxira rasm (telefonda ko'rinadi); MP4 oldindan ko'rish | Har slayd |
| Vizual hakam | Vision-model 7 mezonli rubrika bo'yicha har slaydni baholaydi | o'rtacha ≥ 8.5, hech biri < 7 |

---

## 3. Arxitektura: AI — ssenarist, kod — rejissyor

Hozir: `Mavzu → AI (hamma narsa) → normalize → deck.build`.

Yangi:

```
Mavzu
  → [1] AI SSENARIST     — hikoya: sahnalar (beat), qaysi a'zo skill'i, matn (faqat tekshirilgan faktlardan)
  → [2] REJISSYOR (kod)  — har sahnaga: kompozitsiya, kamera ko'rinishi, harakat (takrorlanmas), yorliqlar
  → [3] SAHNA QURUVCHI   — GLB variantlari: oddiy, kulrang (ghost), kesilgan, ajratilgan, qatlamli
  → [4] PPTX YIG'UVCHI   — uslub tokenlari, yordamchi kadr slaydlari, animMotion oqimlari
  → [5] KO'RISH RENDERI  — three.js (Chromium): zaxira PNG, slayd JPEG, MP4 Morph simulyatsiyasi
  → [6] SIFAT HAKAMI     — avtomatik o'lchovlar + vision rubrika → zaif slayd qayta quriladi
  → Bot: PPTX + MP4 oldindan ko'rish
```

Kim nimani hal qiladi:

| Qaror | Hozir | Yangi |
|---|---|---|
| Qaysi organlar, hikoya tartibi | AI | AI (skill kartasidagi sahnalar menyusidan) |
| Burchak (`rot`) | AI raqam beradi | Kod: skill'dagi **nomlangan ko'rinishlar** ("old", "asos", "cho'qqi") |
| Harakat turi | Yo'q (doim bir xil) | Kod: harakat grammatikasi + takrorlanmaslik algoritmi |
| Kompozitsiya | Yo'q (doim bitta) | Kod: 12 kompozitsiya, sahna turiga qarab |
| Yorliqlar | AI organ ro'yxati | Kod: skill'dagi landmarklar, ko'rinishi va joyi hisoblanadi |
| Matn | AI erkin | AI, lekin faqat skill faktlari + daraja; uzunlik kompozitsiyaga mos |
| Uslub | Yo'q | Mijoz tanlaydi yoki mavzu/daraja bo'yicha avtomatik |

Natija: bir xil mavzu ham har safar boshqacha (urug' — `seed`), lekin har doim mantiqli va silliq.

Yangi modullar (`services/med3d/`): `styles.py`, `compositions.py`, `motion.py` (rejissyor), `skills/` (a'zo kartalari),
`landmarks.py`, `variants.py` (ghost/kesim/ajratish GLB), `flow.py` (oqim yo'llari), `preview/` (three.js),
`judge.py` (sifat hakami).

---

## 4. Dizayn uslublari

### 4.1. Sakkiz uslub

Shriftlar — faqat Windows'da bor shriftlar (PowerPoint ularni almashtirmasin). Fon — PowerPoint'ning o'z
gradienti (`a:gradFill`, yengil) yoki bir marta tayyorlangan PNG (to'r, qog'oz teksturasi).

| # | Uslub | Kayfiyat | Fon | Shrift (sarlavha / matn) | Yorliq uslubi | A'zo rangi | Harakat xarakteri | Kimga |
|---|---|---|---|---|---|---|---|---|
| 1 | **Klinik tun** | Jiddiy, zamonaviy | Radial `#0F1B33 → #05080F`, chetlari xira | Segoe UI Semibold / Segoe UI | Yumaloq kartochka + chiziq + nuqta (hozirgi, sayqallangan) | Tabiiy | Silliq, 2.0–2.6 s | Talaba (sukut) |
| 2 | **Atlas qog'ozi** (Netter/Gray uslubi) | Klassik darslik | Iliq qog'oz `#F4EFE6` + yengil tekstura PNG | Georgia Bold / Cambria | Ingichka qora chiziq, kichik nuqta, nom hoshiyada, lotinchasi kursiv | Tabiiy, yumshoq yorug'lik | Sokin, 2.4–3.0 s | Talaba, mutaxassis |
| 3 | **Golografik HUD** | Kelajak, texnologiya | `#020B14` + to'r va skan chizig'i PNG | Bahnschrift / Consolas (raqamlar) | ⌐ ¬ qavsli HUD qutilar, "COR · 01" kodlari | Moviy monoxrom, fokusdagi a'zo tabiiy rangda | Tez, aniq, 1.2–1.8 s; qiyshiq burchak ruxsat | Maktab, yoshlar |
| 4 | **Muzey vitrinasi** | Nafis, premium | Qora `#0E0E10`, tepadan yorug'lik dog'i, ostida aks-soya ellipsi | Constantia / Segoe UI Light | Minimal, tilla `#C8A96A` ingichka chiziq, kichik bosh harflar | Tabiiy, kuchli kontur yorug'ligi | Sekin aylanish, 2.6–3.2 s | Muqova, xulosa, mutaxassis |
| 5 | **Oq studiya** (Keynote uslubi) | Toza, yorqin | `#FFFFFF → #F2F4F7` | Segoe UI Black / Segoe UI | Raqamli doiralar + pastda izoh ro'yxati | Tabiiy + model ostida yumshoq soya | Ishonchli, 1.6–2.2 s, ko'p yaqinlashish | Hamma uchun |
| 6 | **Chizma (Blueprint)** | Muhandislik | `#0D3B66` + oq to'r PNG | Bahnschrift Light / Consolas | Oq ingichka chiziq, o'lcham belgisi | Och "gips" monoxrom `#E8EEF4` — shakl yaqqol | O'rtacha, ajratish (explode) ko'p | Skelet, suyaklar |
| 7 | **Jurnal (Editorial)** | Hikoya, jurnal sahifasi | `#F7F3EE` | Georgia Bold 54pt / Segoe UI | Kursiv serif nom, qisqa chiziq | Tabiiy | Parallaks, sarlavha harfma-harf Morph | Ommabop mavzular |
| 8 | **Rentgen** | Tana ichiga qarash | `#000814` | Segoe UI / Segoe UI Light | Ingichka moviy chiziq | Orqada och-moviy "arvoh" tana, oldida a'zolar tabiiy | Sokin, yaqinlashish ko'p | Tizimlar tanada qayerda |

Hamma uslubda **rang kodi bir xil** (darsliklardagi kabi): arteriya — qizil, vena — ko'k, nerv — sariq,
limfa — yashil, suyak — fil suyagi rangi. Monoxrom uslublarda (3, 6) bu kod faqat fokusdagi a'zoga qo'llanadi.

### 4.2. Uslub tokenlari (kod)

```python
@dataclass(frozen=True)
class Style:
    key: str                     # "klinik_tun", "atlas", "hud", "muzey", "studiya", "chizma", "jurnal", "rentgen"
    bg: Background               # gradient to'xtash nuqtalari yoki PNG yo'li
    ink: str; muted: str; accent: str; line: str
    font_head: str; font_body: str; font_mono: str
    title_pt: int; body_pt: int
    label: str                   # "pill" | "leader" | "hud" | "numbered" | "caption"
    organ_mode: str              # "natural" | "mono" | "plaster" | "xray"
    lights: str                  # am3d chiroq to'plami: "studio" | "warm_key" | "rim_cool" | "spotlight"
    motion: MotionTaste          # davomiylik oralig'i, ruxsat etilgan harakatlar, energiya egri chizig'i
    compositions: tuple          # shu uslubga mos kompozitsiyalar
```

- **Yorug'lik** uslubning bir qismi: `pptx3d._LIGHTS` va `AMBIENT` hozir bitta — uslubga 4 to'plam
  (studio, iliq asosiy, sovuq kontur, tepadan dog'). Yorug'lik o'zgarishi 3D'ni eng arzon "qimmat" ko'rsatadi.
- **Tanlash:** bot va saytda "🎨 Uslub" (Avto + 8), har biri uchun bir marta tayyorlangan namuna rasm.
  Avto: maktab → HUD/Oq studiya, talaba → Klinik tun/Atlas, mutaxassis → Atlas/Muzey; skelet mavzusi → Chizma.

### 4.3. Kompozitsiyalar (slayd tuzilishi)

Har kompozitsiyada nomlangan Morph elementlari (`!!title`, `!!body`, `!!panel`, `!!kicker`, `!!accent`) bor —
kompozitsiya almashganda matn bloklari ham silliq ko'chadi (parallaks).

| # | Kompozitsiya | Tuzilish | Qachon |
|---|---|---|---|
| K1 | Hero (muqova) | Model katta, markaz-o'ngda; sarlavha chap-pastda juda katta; ustida tizim nomi | 1-slayd |
| K2 | Chap matn / o'ng model | Hozirgi | Oddiy tushuntirish |
| K3 | Ko'zgu | O'ng matn / chap model | K2 dan keyin — matn va model joy almashadi |
| K4 | Yaqin plan | Model slayddan katta (kesilgan), pastda yarim shaffof izoh kartasi | Detal, tekstura |
| K5 | Yorliq halqasi | Model markazda, 4-8 yorliq ikki yonda, sarlavha tepada kichik | Tuzilish, qismlar |
| K6 | Qatlamlar | Model + yonda qatlamlar ro'yxati, joriy qatlam ajratilgan | Qatlam ochish |
| K7 | Kesim | Kesilgan model + "ichki tuzilish" izohi | Ichki bo'shliqlar |
| K8 | Yo'l | Model + raqamli nuqtalar yo'li + pastda bosqichlar | Qon/havo/ovqat oqimi |
| K9 | Raqamlar | Model chapda kichik, o'ngda 3 ta katta raqam (faqat skill faktlaridan) | Fakt sahnasi |
| K10 | Taqqoslash | Ikki model yonma-yon (erkak/ayol, chap/o'ng) umumiy yorliqlar bilan | Farqlar |
| K11 | Viktorina | Raqamli nuqtalar; nomlar bosilganda chiqadi | Mustahkamlash |
| K12 | Xulosa | Model qayta yig'ilgan + 3 ta asosiy fikr | Oxirgi slayd |

Qoidalar: bir xil kompozitsiya ketma-ket ikki marta bo'lmaydi; 10 slaydda kamida 5 xil; K2/K3 navbatlashadi.

---

## 5. Takrorlanmas 3D Morph harakatlari — harakat grammatikasi

### 5.1. Harakatlar lug'ati

PowerPoint Morph bir xil nomli 3D modelning joyi, o'lchami va aylanishini silliq o'zgartiradi. To'g'ri chiziqli
emas yo'l (yoy, spiral) — oraga **yordamchi kadr slaydlari** qo'yib hosil qilinadi (hozirgi `auto`/`advTm=0`
mexanizmining umumlashmasi). Shakl o'zgarishi (kesim, ajratish, qatlam) — **joyida almashish** (bir xil
piksellar, so'ng harakat).

| Kod | Nomi | Nima o'zgaradi | Energiya | Qachon | Cheklov |
|---|---|---|---|---|---|
| ORBIT | Aylanib o'tish | `y` 30–90°; >45° bo'lsa 1 yordamchi kadr (yoy) | 2 | A'zoning boshqa yuzi | Ketma-ket orbitalar bir yo'nalishda (aylanib yurish) |
| CRANE | Kran | `x` 20–45° (tepadan) yoki −20…−40° (pastdan) | 2 | Asos, klapanlar, visseral yuz | x: −60…60 |
| DOLLY_IN | Yaqinlashish | Ramka fokusga, ×1.3–1.6 | 1 | Detal | Hozirgi `ZOOM_LIMIT` |
| DOLLY_OUT | Uzoqlashish | Teskarisi | 1 | Kontekstga qaytish | — |
| TRUCK | Yonga siljish | Model chap↔o'ng, matn qarshi tomonga (parallaks) | 1 | K2↔K3 almashuvi | — |
| SPIN | Orqaga burilish | 180°, 2 yordamchi kadr | 3 | Orqa yuz | Deck'da ≤ 1 |
| DUTCH | Qiyshiq kadr | `z` ±8–12°, keyingi slaydda qaytadi | 2 | Dramatik urg'u | Faqat HUD, Rentgen |
| EXPLODE | Ajratish | Bitta GLB → joyida N ta GLB → markazdan radial siljish | 3 | Suyaklar, qismlar | ≤ 8 bo'lak; deck'da ≤ 2 |
| ASSEMBLE | Yig'ish | Teskarisi | 2 | Xulosa oldidan | EXPLODE dan keyin |
| PEEL | Qatlam ochish | Tashqi qatlam joyida so'nadi, ichkisi qoladi | 2 | Teri→mushak→suyak; perikard→yurak | Skill `qatlamlar` |
| ISOLATE | Ajratib ko'rsatish | Boshqalar joyida kulrang "arvoh" variantga almashadi, fokus rangli qoladi | 2 | Bitta a'zoni kontekstda | — |
| SLICE | Kesim | Joyida kesilgan variant → CRANE bilan ichkariga qarash | 3 | Buyrak, ko'z, yurak | Skill `kesimlar` |
| FLYTHRU | Yo'l bo'ylab uchish | 2–4 yordamchi kadr: fokus a'zolar zanjiri bo'ylab | 3 | Hazm yo'li, nafas yo'li | Kadrlar ≤ 3.5 s jami |
| HANDOFF | Sahna almashish | Eskisi harakat yo'nalishida burilib chiqadi, yangisi qarama-qarshi chetdan shu yo'nalishda kiradi | 2 | Yangi sahna | Yo'nalish oldingi HANDOFF bilan bir xil emas |
| DROP_IN | Tepadan qo'nish | Yangi a'zo 20° qiyalikda tepadan tushib joyiga o'tiradi | 2 | To'plamga a'zo qo'shilishi | — |
| FLOW | Oqim | Slayd ichida: nuqtalar proyeksiyalangan yo'l bo'ylab yuradi (`p:animMotion`) | 2 | Qon, havo, ovqat, siydik | Skill `oqimlar` |
| SCENE | Ichki animatsiya | GLB ichidagi animatsiya (yurak urishi, nafas) yoki Turntable effekti | 3 | Funksiya | **R&D**, 7.4 |
| TEXT_MORPH | Matn Morph'i | Sarlavha `byWord`/`byChar` Morph (qo'shimcha) | — | Bir xil so'zli sarlavhalar | Boshqa harakat bilan birga |

`FLOW` uchun infratuzilma bor: `slide_anim.py` allaqachon `p:animMotion` yozadi ("hover").

### 5.2. Takrorlanmaslik algoritmi (rejissyor)

Har o'tishning **imzosi**: `(harakat, o'q, yo'nalish, kattalik oralig'i, davomiylik oralig'i)`.
Masalan `ORBIT·y·+·60-90·2.4s`.

```
energiya_egri = [2, 1, 2, 3, 2, 1, 3, 2, 2, 1]      # sokin boshlanish → o'rtada cho'qqi → sokin xulosa
har o'tish t uchun:
  nomzodlar = sahna turiga, uslubga, skill'ga va geometriyaga ruxsat etilgan harakatlar
  ball = 3·sahnaga_moslik + 2·energiya_mosligi(egri[t]) + 1.5·skill_imzosi
         − 4·(oxirgi 2 o'tishda shu harakat) − 6·(imzo avval bo'lgan)
         − 2·(harakat ulushi > 25%) + shovqin(seed)
  eng yuqori ball tanlanadi; imzo yoziladi
```

Qat'iy qoidalar:
- Bir xil harakat ketma-ket ikki marta yo'q; bir imzo deck'da bir marta (16+ o'tishda — kamida 6 o'tish oralig'i).
- 10 slaydda ≥ 6 xil harakat turi; hech bir tur > 25%.
- Davomiylik kattalikdan: burchak tezligi taxminan doimiy (≈ 35–45°/s), 1.2–3.0 s; yordamchi kadrlar bilan jami ≤ 3.5 s.
- Ketma-ket orbitalar bir yo'nalishda 3–4 slayd, keyin teskari — "zigzag" yo'q.
- `seed` = mavzu + buyurtma: qayta yaratilsa boshqa ketma-ketlik, bir buyurtma ichida barqaror.
- (Ixtiyoriy) foydalanuvchi xotirasi: oxirgi 3 taqdimotdagi imzolar keyingisida jarimalanadi.

### 5.3. Morph texnik qoidalari

- **Nomlar:** model `!!m3d_<to'plam>`, matn `!!title`/`!!body`, yorliq `lbl_<landmark>` (Morph'siz, kirish animatsiyasi).
- **Yorliqlar harakat vaqtida yashirinadi:** eski yorliqlar o'tishdan oldin so'nadi, yangilari model to'xtagach chiqadi
  (chiziq uchi noto'g'ri joyda "suzib" qolmaydi).
- **Burchak o'rash:** eng qisqa yo'l (hozirgi `smooth_turns`); 180° — faqat SPIN orqali, yordamchi kadrlar bilan.
- **Katta ramka muammosi:** hozir yaqinlashish ramkani 26" gacha kattalashtiradi. Muqobil — ramka o'lchami
  doimiy, kamera yaqinlashadi (`am3d:camera` / "Pan & Zoom"). Morph buni ham silliq o'tkazadimi — **R&D 7.4**.
- **Yordamchi kadr slaydlari** raqamga kirmaydi, yorliqsiz, `advTm=0` (hozirgidek), har biri 0.5–1.2 s.

---

## 6. A'zoni mukammal ko'rsatish — "skill" kartalari

Har a'zo uchun bir marta yoziladigan **ko'rsatish retsepti**. AI uni faqat sahnalar menyusi sifatida ko'radi,
burchak, yorliq, qatlam va oqimni kod oladi. Kartalar `services/med3d/skills/` da, har biri test bilan.

### 6.1. Namuna: Yurak

```python
YURAK = dict(
    id="yurak",
    organlar=["yurak_bolmachalari", "yurak_qorinchalari", "yurak_klapanlari", "aorta_yoyi",
              "yuqori_kovak_vena", "opka_arteriyasi", "toj_arteriyalar"],
    hero=dict(korinish="old_chap", kompozitsiya="K1"),
    korinishlar={                        # anatomik standart ko'rinishlar (rot gradusda)
        "old":      (0, 0, 0),           # facies sternocostalis
        "old_chap": (8, -20, 0),         # hero: biroz chapdan va tepadan
        "chap_yon": (0, -90, 0),         # facies pulmonalis
        "orqa":     (0, 180, 0),         # basis cordis
        "asos":     (55, 0, 0),          # tepadan: klapanlar tekisligi
        "cho'qqi":  (-35, -25, 0),       # pastdan: apex cordis
    },
    qatlamlar=[["toj_arteriyalar"], ["yurak_bolmachalari", "yurak_qorinchalari"], ["yurak_klapanlari"]],
    nuqtalar={                           # organ ichidagi yorliq joylari (landmark)
        "ong_bolmacha":  dict(organ="yurak_bolmachalari", qism=r"right atrium", la="Atrium dextrum"),
        "chap_bolmacha": dict(organ="yurak_bolmachalari", qism=r"left atrium", la="Atrium sinistrum"),
        "chap_qorincha": dict(organ="yurak_qorinchalari", qism=r"left ventricle", geo="chap_yarmi",
                              la="Ventriculus sinister"),
        "cho'qqi":       dict(organ="yurak_qorinchalari", geo="eng_past_chap", la="Apex cordis"),
        "aorta_yoyi":    dict(organ="aorta_yoyi", geo="eng_yuqori", la="Arcus aortae"),
    },
    oqimlar={
        "kichik_qon_aylanish": dict(rang="#2F5DA8",
                                    yol=["yuqori_kovak_vena", "ong_bolmacha", "opka_arteriyasi"]),
        "katta_qon_aylanish":  dict(rang="#C0282D", yol=["chap_bolmacha", "chap_qorincha", "aorta_yoyi"]),
    },
    kesimlar={"tojsimon": dict(tekislik="frontal", korinish="old")},     # SLICE uchun
    imzo=["ISOLATE", "FLOW", "PEEL", "CRANE"],          # shu a'zoda eng ta'sirli harakatlar
    taqiq=["aorta (butun) — yurakni kichraytiradi", "klapanlar qorinchalar bilan bir fokusda"],
    faktlar={                                           # AI matni faqat shulardan; daraja bo'yicha
        1: ["Yurak — taxminan musht kattaligidagi mushakli a'zo", "To'rt bo'shliq: 2 bo'lmacha, 2 qorincha"],
        2: ["Kattalarda massasi taxminan 250–350 g", "Tinch holatda daqiqasiga 60–100 marta qisqaradi"],
        3: ["..."],
    },
    hikoya=["umumiy", "boshliqlar", "klapanlar", "qon_yoli", "toj_tomirlar", "xulosa"],
)
```

Maydonlar:
- **korinishlar** — AI raqam emas, nom tanlaydi ("asos"). Burchak xatosi va sakrashlar yo'qoladi.
- **nuqtalar (landmark)** — organ ichidagi joy: atlas qism nomi (`qism`), topilmasa geometrik qoida (`geo`:
  "eng_yuqori", "chap_yarmi", "eng_past_chap"). Atlaslar farq qiladi: erkakda bo'lmachalar chap/o'ng ajralgan,
  qorinchalar bitta; ayolda qorinchalar ajralgan — shu sababli har nuqta ikkala tanada tekshiriladi.
  Natija: hozirgi "Yurak bo'lmachalari" o'rniga "O'ng bo'lmacha", "Chap qorincha", "Yurak cho'qqisi".
- **qatlamlar** — PEEL tartibi. **kesimlar** — SLICE tekisligi. **oqimlar** — FLOW yo'li (a'zolar/nuqtalar zanjiri;
  yo'l nuqtalari 3D'da hisoblanib slaydga proyeksiyalanadi va `animMotion` yo'liga aylanadi).
- **faktlar** — tekshirilgan qisqa faktlar, daraja bo'yicha. AI ulardan matn tuzadi, yangi raqam to'qimaydi.
- **taqiq** — hozir `SYSTEM` promptdagi 9-qoidaga o'xshash bilimlar a'zo kartasiga ko'chadi.

### 6.2. A'zolar va ularning "imzo" sahnalari

1-to'lqin (eng ko'p so'raladigan 10 ta):

| A'zo | Hero ko'rinish | Imzo sahna | Maxsus texnika |
|---|---|---|---|
| Yurak | Old, 20° chapdan | Qon yo'li: vena → o'ng bo'lmacha → o'pka arteriyasi; chap tomon → aorta | ISOLATE bo'shliqlar, FLOW ko'k/qizil, CRANE klapanlarga |
| O'pkalar (ayol atlasi) | Old | Havo yo'li: hiqildoq → traxeya → bronxlar | PEEL o'pka → bronx daraxti, ORBIT bo'laklarga |
| Bosh miya | Chap yon | Bo'laklar rangda (peshona, tepa, chakka, ensa) | ISOLATE bo'laklar, CRANE tepadan (bo'ylama egat), PEEL → talamus, gippokamp |
| Bosh suyagi | Old 3/4 | "Ajralgan bosh suyagi" (klassik Beauchene) | EXPLODE 8 suyak, pastki jag' DROP_IN |
| Umurtqa pog'onasi | Yon (egriliklar) | Bo'limlar rangda: bo'yin, ko'krak, bel, dumg'aza | EXPLODE vertikal "akkordeon", disklar, ichida orqa miya |
| Hazm tizimi | Old | Ovqat yo'li bo'ylab uchish | FLYTHRU + FLOW, ISOLATE jigar/oshqozon osti bezi |
| Jigar | Pastdan (visseral yuz) | O't pufagi va o't yo'llari | CRANE −40°, ISOLATE segmentlar (mutaxassis) |
| Buyraklar | Old | Ichki tuzilish (piramida, kosachalar, jom) | SLICE frontal, FLOW siydik → siydik pufagi |
| Ko'z olmasi | 3/4 | Qavatlar: shox parda, gavhar, shishasimon tana, to'r parda | SLICE sagittal, EXPLODE qavatlar |
| Skelet | Butun tana | O'q va qo'l-oyoq skeleti | DOLLY bo'limlarga, ISOLATE rangli bo'limlar |

2-to'lqin: hiqildoq, oshqozon, ichaklar, taloq, bachadon va naylar, homiladorlik (yo'ldosh), tizza bo'g'imi,
mushaklar (ko'krak, yelka, son), ko'z mushaklari, orqa miya. 3-to'lqin: qolgan ~70 organ — avtomatik karta
(geometriyadan hero ko'rinish va nuqtalar) + qo'lda tekshiruv.

### 6.3. A'zoni "o'qitadigan" qo'shimcha elementlar

- **Anatomik kompas:** burchakda kichik o'qlar (Superior/Inferior, Dexter/Sinister, Anterior/Posterior) — har slaydda
  `rot` bo'yicha hisoblanadi, Morph ular bilan birga aylantiradi. Talaba "chap-o'ng"ni adashtirmaydi.
- **Masshtab chizig'i:** "5 sm" chizig'i — atlas birligi metr, kamera proyeksiyasi ma'lum, shuning uchun aniq.
- **O'qituvchi rejimi:** yorliqlar bosilganda birma-bir chiqadi (hozir — avtomatik).
- **Viktorina (K11):** avval raqamli nuqtalar, bosilganda nomlar.
- **Ichki navigatsiya:** umumiy slayddagi a'zo yorlig'i bosilsa — o'sha a'zo bo'limiga o'tadi, "← umumiy" tugmasi.

### 6.4. Ishlab chiquvchi skill'i

`.claude/skills/organ-skill/SKILL.md` — yangi a'zo kartasini qo'shish tartibi: atlas nomlarini tekshirish,
nuqtalarni ikkala tanada sinash, faktlarni manba bilan yozish, test qo'shish, preview'da ko'rish. Keyingi
Claude sessiyalari kartalarni bir xil sifatda qo'shadi.

---

## 7. Texnik poydevor (bularsiz 9/10 bo'lmaydi)

### 7.1. Haqiqiy zaxira rasm va telefonda ko'rish
Hozir `mc:Fallback` — 1×1 bo'sh PNG. Har model nusxasi uchun three.js bilan shu kamera va yorug'likda chizilgan
shaffof PNG (1024 px) qo'yiladi. Natija: telefon, WPS, Google Slides, Keynote, eski PowerPoint'da slayd bo'sh
emas; botdagi "faqat kompyuterda oching" ogohlantirishi yumshaydi.

### 7.2. Ko'rish rendereri va Morph simulyatori (repoga qo'shiladi)
Playwright + Chromium (serverda bor) + three.js: `deck_plan` → har slayd JPEG + o'tishlar kadrlari → **MP4**.
Bot taqdimot bilan birga 20–40 soniyalik MP4 yuboradi — mijoz harakatni telefonda darhol ko'radi.

### 7.3. Avtomatik sifat hakami
1. **Geometrik tekshiruvlar (bepul):** yorliqlar ustma-ust emas; chiziq uchi ko'rinadigan joyda; matn sig'adi;
   model kompozitsiya hududining 35–70% ini egallaydi; takrorlanmaslik indeksi; burchak tezligi.
2. **Vision rubrika (arzon model, ~1 so'rov / slayd):** kompozitsiya, kontrast, a'zo aniq ko'rinadimi, yorliq
   to'g'ri joydami, matn va rasm mosligi, estetika, o'qilishi — har biri 1–10, JSON.
3. 7 dan past slayd — rejissyor boshqa variant bilan qayta quradi (≤ 2 urinish).

### 7.4. PowerPoint'da tekshirish — kalibrlash taqdimoti
Linux'da PowerPoint yo'q. Bir marta 12 slaydli sinov fayli yasaladi. Siz PowerPoint 365 da ochib, ekranni yozib
yuborasiz (≈ 15 daqiqa):

1. Aylanish yo'nalishi (`camera.SIGN`) — yorliq nuqtalari to'g'ri joydami.
2. Yordamchi slayd o'zi o'tadimi, joyida almashishda "miltillash" bormi.
3. Kamera yaqinlashishi (Pan & Zoom) Morph bilan silliq o'tadimi → katta ramka muammosi yechimi.
4. GLB ichidagi animatsiya (tugun masshtabi: yurak urishi) "Scenes" sifatida o'ynaydimi.
5. Turntable / Swing effekti — **etalon fayl:** PowerPoint'da bitta modelga Turntable qo'shib saqlab yuborasiz,
   XML'ini ko'chiramiz.
6. "Arvoh" tana: alohida orqa qatlamdagi och model (PowerPoint modellar orasida chuqurlikni solishtirmaydi —
   shu xususiyatdan foydalanamiz) va `MASK` rejimidagi shaffoflik. `BLEND` ishonchsiz — ishlatilmaydi.
7. EXPLODE: 8 model bir vaqtda turli yo'nalishda.
8. 26" ramka tezligi. 9. Sarlavha `byChar` Morph. 10. `animMotion` oqim nuqtalari. 11. Giperhavola navigatsiya.
12. Uslublar shriftlari (Bahnschrift, Constantia) almashtirilmaydimi.

### 7.5. Hajm va tezlik
Hozirgi 45 MB chegara saqlanadi. GLB variantlari (ghost, kesim, ajratilgan) qo'shilganda hajm o'sadi: ghost — 10–20%
sifatda (shakl yetarli), kesim — faqat kesilgan a'zo, bir xil GLB bir marta (`parts` keshi, hozirgidek).

---

## 8. 3D Pro (rasm asosidagi) uchun

- **Uslublar va kompozitsiyalar** shu rejadagidan (4-bo'lim) — `pro3d.build.PALETTES` 7 ta rang, tuzilish bitta.
- **2D harakat grammatikasi:** Morph rasmning joyi, o'lchami, aylanishi va qirqimini (crop) silliq o'zgartiradi →
  DOLLY (qirqim orqali yaqinlashish), TRUCK + parallaks (fon shakli, obyekt, old bezak — 3 qatlam turli tezlikda),
  doira→to'rtburchak niqob ochilishi, ajratilgan panel. Takrorlanmaslik algoritmi o'sha.
- **R&D — rasmni haqiqiy 3D'ga aylantirish:** fal.ai'da image-to-3D modellar bor (Hunyuan3D v2 ≈ $0.16,
  Tripo v2.5 ≈ $0.20–0.40 bir model; narxlar o'zgarishi mumkin). `FAL_API_KEY` loyihada bor. Obyekt rasmi → GLB →
  `med3d.pptx3d.add_model3d` → 3D Pro'da ham haqiqiy aylanish. 10 obyektli taqdimot ≈ $1.6–4; `PRICE_FACTOR=3`
  bilan solishtirib qaror qilinadi.

---

## 9. Yo'l xaritasi

| Bosqich | Nima | Qabul mezoni | Kutilgan ball |
|---|---|---|---|
| **0** ✅ | #208–#211 tiklash | Testlar o'tdi (shu shox) | 4 |
| **1** | Ko'rish rendereri, haqiqiy zaxira PNG, MP4 oldindan ko'rish, sifat hakami (o'lchov) | 5 mavzu bo'yicha joriy taqdimotlar baholandi (asos chiziq); telefonda slaydlar ko'rinadi | 5 |
| **2** | Rejissyor: harakat grammatikasi (ORBIT, CRANE, DOLLY, TRUCK, SPIN, HANDOFF, DROP_IN), takrorlanmaslik, 12 kompozitsiya, yorliq harakat vaqtida yashirinishi | Takrorlanmaslik indeksi ≥ 0.9, ≥ 6 harakat turi / 10 slayd; `test_med3d_motion.py` | 6.5 |
| **3** | 8 dizayn uslubi, 4 yorug'lik to'plami, bot/saytda "🎨 Uslub" | Har uslubda 3 mavzu render qilindi; vision "estetika" ≥ 8 | 7.5 |
| **4** | Skill kartalari 1-to'lqin (10 a'zo), landmarklar, faktlar, nomlangan ko'rinishlar, kompas, masshtab | Har a'zoda ≥ 8 landmark ikkala tanada; faktlar 100% kartadan | 8.5 |
| **5** | Maxsus sahnalar: ISOLATE, PEEL, SLICE, EXPLODE/ASSEMBLE, FLYTHRU, FLOW; Rentgen uslubi | Har imzo sahna 1-to'lqin a'zolarida ishlaydi; vision o'rtacha ≥ 8.5 | 9 |
| **6** | R&D (7.4 natijasiga qarab): GLB animatsiya (yurak urishi, nafas), Turntable, kamera Morph; 3D Pro → GLB | Kalibrlash taqdimoti PowerPoint'da tasdiqlandi | 9+ |
| **7** | Interaktivlik (viktorina, o'qituvchi rejimi, navigatsiya), skill 2-3 to'lqin, `organ-skill` SKILL.md | 30+ a'zo kartasi | 9.5 |

**Ketma-ketlik sababi:** avval ko'rish va o'lchash (1) — ko'rmagan narsani yaxshilab bo'lmaydi. Keyin eng ko'p
seziladigan harakat va kompozitsiya (2), so'ng uslub (3), keyin chuqurlik (4–5). R&D (6) parallel: kalibrlash
taqdimoti 1-bosqich bilan birga tayyorlanadi.

Har bosqich — alohida PR, o'z testlari bilan (`test_med3d_*.py` uslubida), hech biri mavjud oqimni buzmaydi:
yangi imkoniyat sukut bo'yicha yoqiladi faqat sifat hakami tasdiqlagandan keyin.

---

## 10. Xavflar va ochiq savollar

| Xavf | Ta'sir | Yechim |
|---|---|---|
| PowerPoint xatti-harakati Linux'da tekshirilmaydi | Harakat/yorliq noto'g'ri chiqishi | 7.4 kalibrlash taqdimoti; har yangi texnika avval shu faylda |
| GLB shaffofligi (`BLEND`) PowerPoint'da ishonchsiz | Rentgen uslubi | Orqa qatlamdagi alohida "arvoh" model + `MASK`; `BLEND` ishlatilmaydi |
| GLB variantlari hajmni oshiradi | 45 MB dan oshish | Ghost past sifatda, kesim faqat kerakli a'zo, `make_deck` sifat pasaytirishi |
| Atlas nomlari erkak/ayolda farqli | Landmark topilmaydi | `qism` + `geo` zaxira; har nuqta ikkala tanada testlanadi |
| Tibbiy aniqlik | Ishonch yo'qolishi | Faktlar kartada; o'zbekcha atamalarni shifokor bir marta ko'rib chiqadi |
| Ayol atlasida bosh suyagi, qo'l-oyoq suyaklari yo'q (erkakdan olingan) | Ayolga xos emas | Skill kartasida tana tanlovi qoidasi (hozirgidek) |
| Mac'da Bahnschrift yo'q | Shrift almashadi | Uslubda zaxira shrift; 7.4-12 tekshiruv |

## 11. Sizdan kerak bo'ladigan narsalar

1. **Bu shoxni `main` ga qo'shish** (aks holda 3D Anatomiya va #210/#211 tuzatishlari botda yo'q).
2. 1-bosqich tugagach — kalibrlash taqdimotini PowerPoint 365 da ochib, ekran yozuvini yuborish va bitta
   Turntable effektli etalon fayl.
3. Uslublar ro'yxatini tasdiqlash yoki o'zgartirish (8 ta; kerak bo'lmaganini olib tashlash mumkin).
4. 1-to'lqin a'zolari tartibi (o'quvchilaringiz eng ko'p qaysi mavzularni so'rashi).
5. 3D Pro → GLB (fal.ai) uchun xarajat qarori.
