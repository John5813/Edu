"""Organlar lug'ati: AI tanlay oladigan organlar, ularning o'zbekcha nomi, rangi va atlasdagi qismlari.

Atlaslarda (erkak — BodyParts3D, ayol — Human Reference Atlas) nomlar bir xil emas va doim mantiqiy emas
(masalan, erkak jigari "Hepatovenous segment" deb vena tizimida turibdi). Shuning uchun AI xom nomlar bilan
emas, shu tekshirilgan ro'yxat bilan ishlaydi. `tools/med3d_lugat.py` qoidalarni atlasga qo'llab
`assets/med3d/lugat.json` ni yasaydi (har organ uchun qism id lari, chegara qutisi, yorliq nuqtalari).

Qoida yozilishi: "regex" — nomda qidiriladi (katta-kichik harf farqsiz); "tizim:regex" — faqat shu
tizimdagi qismlar ("skeletal|borrowed:..." — bir nechta tizim); "id:FJ2823" — aniq bitta qism.
`m` — erkak, `f` — ayol; bo'sh bo'lsa — shu tanada yo'q. `union` — boshqa organlar yig'indisi.
`tones` — organ ichidagi qismlarga alohida rang [(regex, rang)]; `union` organ esa tarkibidagi organlar
rangida chiziladi (masalan, yurak: bo'lmachalar och, qorinchalar to'q).
`shade` — soyadagi (egat, chuqurlik) rang: sukut bo'yicha organ rangining to'qrog'i.
`inside` — bu organni o'rab turgan organlar: kamera shu organga yaqinlashsa, ular slayddan chiqariladi
(aks holda organ ko'rinmaydi, masalan klapanlar yurak ichida).
"""
from typing import Dict, List

BONE, TOOTH, CARTILAGE = "#DDD0B3", "#F1ECDF", "#A9C3D1"
MUSCLE, TENDON = "#B0423C", "#D8C9A8"
ARTERY, VEIN, HEART = "#C0282D", "#2F5DA8", "#9E2B2B"
NERVE, BRAIN = "#E3C35A", "#D9927E"
FAT, SKIN = "#E7C47C", "#D9A98C"

_SKULL = r"^(left |right )?(frontal bone|parietal bone|occipital bone|temporal bone|sphenoid bone|ethmoid|maxilla|" \
         r"zygomatic bone|nasal bone|palatine bone|vomer|mandible|lacrimal bone|inferior nasal concha)$"
_HAND = r"(scaphoid|lunate|triquetral|pisiform|trapezium|trapezoid|capitate|hamate|metacarpal|" \
        r"phalanx of (thumb|index finger|middle finger|ring finger|little finger))"
_FOOT = r"(talus|calcaneus|navicular bone of foot|cuboid bone|cuneiform bone|metatarsal|" \
        r"phalanx of (big|second|third|fourth|little) toe|sesamoid bone of foot)"
_LR = r"^(left |right )?"

ORGANS: List[Dict] = [
    # ── Skelet
    dict(id="bosh_suyagi", uz="Bosh suyagi", en="Skull", color=BONE,
         m=["skeletal|sensory|respiratory:" + _SKULL], f=["borrowed:" + _SKULL]),
    dict(id="pastki_jag", uz="Pastki jag'", en="Mandible", color=BONE,
         m=["skeletal:^mandible$"], f=["borrowed:^mandible$"]),
    dict(id="tishlar", uz="Tishlar", en="Teeth", color=TOOTH,
         m=["skeletal:secondary .*tooth$"], f=["digestive:^set of (lower|upper) jaw teeth$"]),
    dict(id="umurtqa", uz="Umurtqa pog'onasi", en="Vertebral column", color=BONE,
         m=["skeletal:(vertebra$|^atlas$|^axis$|^sacrum$|coccyx)"], f=[r"skeletal:(vertebra \d+$|^sacrum$|^coccyx$)"]),
    dict(id="umurtqa_disklari", uz="Umurtqalararo disklar", en="Intervertebral discs", color=CARTILAGE,
         m=["skeletal:intervertebral disk"], f=["connective:^intervertebral disk"]),
    dict(id="qovurgalar", uz="Qovurg'alar", en="Ribs", color=BONE,
         m=["skeletal:( rib$|costal cartilage)"], f=["borrowed:( rib$|costal cartilage)"]),
    dict(id="tosh_suyagi", uz="To'sh suyagi", en="Sternum", color=BONE,
         m=["skeletal:^(body of sternum|manubrium|xiphoid process)$"], f=["skeletal:^(sternum|manubrium)$"]),
    dict(id="umrov", uz="O'mrov suyagi", en="Clavicle", color=BONE,
         m=["skeletal:" + _LR + "clavicle$"], f=["borrowed:" + _LR + "clavicle$"]),
    dict(id="kurak", uz="Kurak suyagi", en="Scapula", color=BONE,
         m=["skeletal:" + _LR + "scapula$"], f=["borrowed:" + _LR + "scapula$"]),
    dict(id="yelka_suyagi", uz="Yelka suyagi", en="Humerus", color=BONE,
         m=["skeletal:" + _LR + "humerus$"], f=["borrowed:" + _LR + "humerus$"]),
    dict(id="bilak_suyaklari", uz="Bilak suyaklari", en="Radius and ulna", color=BONE,
         m=["skeletal:" + _LR + "(radius|ulna)$"], f=["borrowed:" + _LR + "(radius|ulna)$"]),
    dict(id="qol_panja", uz="Qo'l panjasi suyaklari", en="Hand bones", color=BONE,
         m=["skeletal:" + _HAND], f=["borrowed:" + _HAND]),
    dict(id="chanoq", uz="Chanoq suyagi", en="Hip bone (pelvis)", color=BONE,
         m=["skeletal:hip bone$"], f=["skeletal:(ilium|ischium|pubis) compact bone"]),
    dict(id="son_suyagi", uz="Son suyagi", en="Femur", color=BONE,
         m=["skeletal:" + _LR + "femur$"], f=["skeletal:(^femur|condyle of femur|intercondylar fossa|trochlear groove)"]),
    dict(id="tizza_qopqogi", uz="Tizza qopqog'i", en="Patella", color=BONE,
         m=["skeletal:" + _LR + "patella$"], f=["skeletal:^patella"]),
    dict(id="boldir_suyaklari", uz="Katta va kichik boldir suyaklari", en="Tibia and fibula", color=BONE,
         m=["skeletal:" + _LR + "(tibia|fibula)$"], f=["skeletal:^(tibia|fibula)"]),
    dict(id="oyoq_panja", uz="Oyoq panjasi suyaklari", en="Foot bones", color=BONE,
         m=["skeletal:" + _FOOT], f=["borrowed:" + _FOOT]),
    dict(id="skelet", uz="Skelet", en="Whole skeleton", color=BONE,
         union=["bosh_suyagi", "umurtqa", "qovurgalar", "tosh_suyagi", "umrov", "kurak", "yelka_suyagi",
                "bilak_suyaklari", "qol_panja", "chanoq", "son_suyagi", "tizza_qopqogi", "boldir_suyaklari",
                "oyoq_panja"]),
    dict(id="tizza_boylamlari", uz="Tizza bo'g'imi boylamlari va menisklar", en="Knee ligaments and menisci",
         color=CARTILAGE, m=[], f=["connective:(cruciate|collateral ligament|anterolateral ligament|meniscus|"
                                   "articular cartilage of knee)"]),

    # ── Mushaklar
    dict(id="mushaklar", uz="Skelet mushaklari", en="Skeletal muscles", color=MUSCLE,
         m=["muscular:^(?!.*(papillary|rectus$|oblique$|levator palpebrae)).*"],
         f=["donor-muscle:.*"]),
    dict(id="diafragma", uz="Diafragma", en="Diaphragm", color=MUSCLE, m=["muscular:^diaphragm$"], f=[]),
    dict(id="kokrak_mushagi", uz="Katta ko'krak mushagi", en="Pectoralis major", color=MUSCLE,
         m=["muscular:pectoralis major"], f=[]),
    dict(id="deltasimon", uz="Deltasimon mushak", en="Deltoid", color=MUSCLE, m=["muscular:deltoid"], f=[]),
    dict(id="trapetsiyasimon", uz="Trapetsiyasimon mushak", en="Trapezius", color=MUSCLE,
         m=["muscular:trapezius"], f=[]),
    dict(id="qorin_mushaklari", uz="Qorinning tashqi qiyshiq mushagi", en="External oblique", color=MUSCLE,
         m=["muscular:external oblique"], f=[]),
    dict(id="qovurgalararo", uz="Qovurg'alararo mushaklar", en="Intercostal muscles", color=MUSCLE,
         m=["muscular:intercostal"], f=[]),
    dict(id="yelka_mushaklari", uz="Yelkaning ikki va uch boshli mushaklari", en="Biceps and triceps brachii",
         color=MUSCLE, m=["muscular:(biceps|triceps) brachii"], f=[]),
    dict(id="dumba_mushaklari", uz="Dumba mushaklari", en="Gluteal muscles", color=MUSCLE,
         m=["muscular:gluteus"], f=["donor-muscle:gluteus"]),
    dict(id="son_mushaklari", uz="Son mushaklari", en="Thigh muscles", color=MUSCLE,
         m=["muscular:(rectus femoris|vastus|sartorius|biceps femoris|semitendinosus|semimembranosus|"
            "adductor (longus|brevis|magnus)|gracilis|pectineus)"],
         f=["donor-muscle:(rectus femoris|vastus|sartorius|biceps femoris|semitendinosus|semimembranosus|"
            "adductor (longus|brevis|magnus)|gracilis|pectineus)"]),
    dict(id="boldir_mushaklari", uz="Boldir mushaklari", en="Leg (calf) muscles", color=MUSCLE,
         m=["(gastrocnemius|soleus|tibialis (anterior|posterior)|fibularis)"],
         f=["donor-muscle:(gastrocnemius|soleus|tibialis|peroneus|plantaris|popliteus)"]),

    # ── Yurak va qon tomirlari
    dict(id="yurak_bolmachalari", uz="Yurak bo'lmachalari", en="Atria of the heart", color="#C9605A",
         m=["cardiac:^wall of (left|right) atrium$"], f=["cardiac:cardiac atrium"]),
    dict(id="yurak_qorinchalari", uz="Yurak qorinchalari", en="Ventricles of the heart", color=HEART,
         m=["cardiac:^wall of ventricle$"], f=["cardiac:(^(left |right )?ventricle|interventricular septum)"]),
    dict(id="yurak_klapanlari", inside=['yurak', 'yurak_qorinchalari', 'yurak_bolmachalari'], uz="Yurak klapanlari", en="Heart valves", color="#E8D7A8",
         m=["cardiac:(cusp|leaflet)"], f=["cardiac:valve"]),
    dict(id="yurak", uz="Yurak", en="Heart", color=HEART,
         union=["yurak_bolmachalari", "yurak_qorinchalari"]),
    dict(id="aorta", uz="Aorta", en="Aorta", color=ARTERY,
         m=["arterial:^(ascending aorta|arch of aorta|descending aorta|descending thoracic aorta|abdominal aorta)$"],
         f=["arterial:^(ascending aorta|aortic arch|descending aorta)"]),
    dict(id="aorta_yoyi", uz="Ko'tariluvchi aorta va aorta yoyi", en="Ascending aorta and aortic arch",
         color=ARTERY, m=["arterial:^(ascending aorta|arch of aorta)$"], f=["arterial:^(ascending aorta|aortic arch)"]),
    dict(id="yuqori_kovak_vena", uz="Yuqori kovak vena", en="Superior vena cava", color=VEIN,
         m=["venous:^superior vena cava$"], f=["venous:^superior vena cava$"]),
    dict(id="opka_arteriyasi", uz="O'pka arteriyasi", en="Pulmonary trunk and arteries", color="#3F6FC0",
         m=["arterial:pulmonary (trunk|artery)"], f=["arterial:pulmonary (trunk|artery)"]),
    dict(id="kovak_venalar", uz="Kovak venalar", en="Venae cavae", color=VEIN,
         m=["venous:vena cava"], f=["venous:vena cava"]),
    dict(id="toj_arteriyalar", uz="Yurakning toj arteriyalari", en="Coronary arteries", color=ARTERY,
         m=["arterial:coronary artery"],
         f=["arterial:(coronary artery|anterior descending|circumflex|^(left |right )?marginal artery$|"
            "marginal branch|diagonal branch|posterior ventricular branch)"]),
    dict(id="arteriyalar", uz="Arteriyalar", en="Arteries", color=ARTERY, m=["arterial:.*"], f=["arterial:.*"]),
    dict(id="venalar", uz="Venalar", en="Veins", color=VEIN,
         m=["venous:^(?!hepatovenous segment).*"], f=["venous:.*"]),

    # ── Nafas tizimi
    dict(id="hiqildoq", uz="Hiqildoq", en="Larynx", color=CARTILAGE,
         m=["(thyroid cartilage|cricoid cartilage|arytenoid cartilage|corniculate cartilage|cuneiform cartilage|"
            "^epiglottis$)"],
         f=["respiratory:(thyroid cartilage|cricoid cartilage|arytenoid cartilage|corniculate cartilage|"
            "epiglotic cartilage)"]),
    dict(id="traxeya", uz="Traxeya (kekirdak)", en="Trachea", color=CARTILAGE,
         m=["respiratory:^trachea$"], f=["respiratory:^(trachea|tracheal cartilage|carina)$"]),
    dict(id="bronxlar", inside=['opkalar', 'ong_opka', 'chap_opka'], uz="Bronxlar", en="Bronchi", color="#C9D6DF",
         m=["respiratory:(bronch)"], f=["respiratory:bronch(?!opulmonary)"]),
    dict(id="opkalar", uz="O'pkalar", en="Lungs", color="#D88E94",
         m=[], f=["respiratory:bronchopulmonary segment"]),
    dict(id="ong_opka", uz="O'ng o'pka", en="Right lung", color="#D88E94",
         m=[], f=["respiratory:^right .*bronchopulmonary segment"]),
    dict(id="chap_opka", uz="Chap o'pka", en="Left lung", color="#D88E94",
         m=[], f=["respiratory:^(left .*|lingula .*)bronchopulmonary segment"]),
    dict(id="halqum", uz="Halqum mushaklari", en="Pharyngeal constrictors", color=MUSCLE,
         m=["pharyngeal constrictor"], f=[]),

    # ── Hazm tizimi
    dict(id="til", uz="Til", en="Tongue", color="#B04F58",
         m=["digestive:^tongue$"], f=["digestive:(dorsal tongue|ventral tongue|posterior part of tongue)"]),
    dict(id="solak_bezlari", uz="So'lak bezlari", en="Salivary glands", color="#D29C4E",
         m=["digestive:(sublingual gland|submandibular gland)"],
         f=["digestive:(parotid gland|sublingual gland|submandibular gland)"]),
    dict(id="qizilongach", uz="Qizilo'ngach", en="Esophagus", color="#B65A62", m=["digestive:^esophagus$"], f=[]),
    dict(id="oshqozon", uz="Oshqozon", en="Stomach", color="#BC5A62", m=["digestive:^stomach$"], f=[]),
    dict(id="jigar", uz="Jigar", en="Liver", color="#74261F",
         m=["digestive:^caudate lobe of liver$",
            "venous:^hepatovenous segment (ii|iii|iv|v|vi)$", "id:FJ2823", "id:FJ2824"],
         f=["digestive:^capsule of the liver$"]),
    dict(id="ot_pufagi", uz="O't pufagi", en="Gallbladder", color="#3F7F31",
         m=["digestive:^gallbladder$"], f=["digestive:^gallbladder$"]),
    dict(id="ot_yollari", inside=['jigar'], uz="O't yo'llari", en="Bile ducts", color="#3F7F31",
         m=["digestive:^(cystic duct|common hepatic duct)$"],
         f=["digestive:^(cystic duct|common hepatic duct|common bile duct|(left |right )?hepatic duct)"]),
    dict(id="oshqozon_osti", uz="Oshqozon osti bezi", en="Pancreas", color="#D29D47",
         m=["digestive:^pancreas$"], f=["digestive:((head|neck|body|tail) of pancreas|uncinate process)"]),
    dict(id="onikki_barmoq", uz="O'n ikki barmoq ichak", en="Duodenum", color="#C27650",
         m=["digestive:^duodenum$"], f=["digestive:^duodenum"]),
    dict(id="ingichka_ichak", uz="Ingichka ichak", en="Small intestine (jejunum and ileum)", color="#C9706E",
         m=["digestive:(jejunum|ileum|ileocecal junction)"], f=["digestive:^(jejunum|ileum)"]),
    dict(id="yogon_ichak", uz="Yo'g'on ichak", en="Large intestine (colon)", color="#9C5843",
         m=["digestive:^(ascending colon|transverse colon|descending colon|appendix)$"],
         f=["digestive:^(caecum|ascending colon|transverse colon|descending colon|sigmoid colon|"
            "hepatic flexure of colon|splenic flexure of colon|vermiform appendix)$"]),
    dict(id="togri_ichak", uz="To'g'ri ichak", en="Rectum", color="#8E4A3A",
         m=["digestive:^rectum$"], f=["digestive:^rectum$"]),

    # ── Siydik ajratish tizimi
    dict(id="buyraklar", uz="Buyraklar", en="Kidneys", color="#8C3B2E",
         m=["urinary:" + _LR + "kidney$"], f=["urinary:^kidney capsule"]),
    dict(id="buyrak_ichki", inside=['buyraklar'], uz="Buyrakning ichki tuzilishi", en="Internal structure of the kidney",
         tones=[("renal pyramid", "#7E2A26"), ("renal papilla", "#B5523F"), ("calyx|renal pelvis", "#D9B05A"),
                ("renal column", "#C98B7A")],
         color="#A7493A", m=[], f=["urinary:(renal pyramid|renal papilla|calyx|renal pelvis|renal column)"]),
    dict(id="siydik_naylari", uz="Siydik naylari", en="Ureters", color="#D6B25E",
         m=["urinary:" + _LR + "ureter$"], f=["urinary:^ureter"]),
    dict(id="siydik_pufagi", uz="Siydik pufagi", en="Urinary bladder", color="#D9A35B",
         m=["urinary:^urinary bladder$"], f=["urinary:(urinary bladder|trigone of urinary bladder)"]),
    dict(id="siydik_kanali", uz="Siydik chiqarish kanali", en="Urethra", color="#D9A35B",
         m=["urinary:^urethra$"], f=[]),

    # ── Jinsiy a'zolar va homiladorlik
    dict(id="moyaklar", uz="Moyaklar", en="Testes", color="#D7A0A0", m=["reproductive:testis$"], f=[]),
    dict(id="moyak_ortigi", uz="Moyak ortig'i", en="Epididymis", color="#C98585",
         m=["reproductive:epididymis$"], f=[]),
    dict(id="urug_yoli", uz="Urug' chiqaruv yo'li", en="Vas deferens", color="#C9A15B",
         m=["reproductive:deferent duct$"], f=[]),
    dict(id="urug_pufakchalari", uz="Urug' pufakchalari", en="Seminal vesicles", color="#C9A15B",
         m=["reproductive:seminal vesicle$"], f=[]),
    dict(id="prostata", uz="Prostata bezi", en="Prostate", color="#B9744E", m=["reproductive:^prostate$"], f=[]),
    dict(id="jinsiy_olat", uz="Jinsiy olat", en="Penis", color="#C98D7A",
         m=["reproductive:(corpus cavernosum|corpus spongiosum|glans penis)"], f=[]),
    dict(id="bachadon", uz="Bachadon", en="Uterus", color="#C25D6E", m=[],
         f=["reproductive:^(body of uterus|fundus of uterus|anterior wall of uterus|posterior wall of uterus|"
            "lower uterine segment|cornua)$"]),
    dict(id="bachadon_boyni", uz="Bachadon bo'yni", en="Cervix", color="#B04B5C", m=[],
         f=["reproductive:^(cervix|internal cervical os|external cervical os|cervicovaginal junction)$"]),
    dict(id="bachadon_naylari", uz="Bachadon naylari", en="Uterine (fallopian) tubes", color="#C25D6E", m=[],
         f=["reproductive:(uterine tube|fallopian tube|abdominal ostium)"]),
    dict(id="tuxumdonlar", uz="Tuxumdonlar", en="Ovaries", color="#E0B06A", m=[], f=["reproductive:ovary$"]),
    dict(id="qin", uz="Qin", en="Vagina", color="#B85A6A", m=[], f=["reproductive:^vagina$"]),
    dict(id="bachadon_boylamlari", uz="Bachadon va tuxumdon boylamlari", en="Uterine and ovarian ligaments",
         color="#D9B8A0", m=[],
         f=["reproductive:(ligament of uterus|broad ligament|uterosacral|ovarian ligament|"
            "suspensory ligament of ovary)"]),
    dict(id="yoldosh", inside=['amnion'], uz="Yo'ldosh", en="Placenta", color="#8E2F45", m=[],
         f=["pregnancy:^(basal plate|chorionic plate)$"]),
    dict(id="yoldosh_tomirlari", inside=['amnion'], uz="Yo'ldosh va kindik tomirlari", en="Placental and umbilical vessels",
         color="#4F63B0", m=[], f=["pregnancy:(placenta vessels|umbilical artery|umbilical vein)"]),
    dict(id="kindik", inside=['amnion'], uz="Kindik tizimchasi", en="Umbilical cord", color="#C7B6C9", m=[],
         f=["pregnancy:^umbilical cord$"]),
    dict(id="amnion", uz="Amnion pardasi", en="Amnion", color="#D9C3C8", m=[], f=["pregnancy:^amnion$"]),
    dict(id="sut_bezi", inside=['teri'], uz="Sut bezi", en="Mammary gland", color="#E3A6A0", m=[],
         f=["integumentary:(mammary lobes|lactiferous|nipple|areola)"]),

    # ── Nerv tizimi
    # Bosh miya: katta yarimsharlar iliq pushti-qo'ng'ir, miyacha to'qroq jigarrang, miya ustuni och sarg'ish;
    # egatlar qizg'ish-qoramtir soyada (shade) — tabiiy miya ko'rinishiga yaqin.
    dict(id="bosh_miya", uz="Bosh miya", en="Brain", color=BRAIN, shade="#4A1622",
         tones=[("cerebell", "#9A6048"), ("pons|medulla|midbrain|peduncle|tegmentum", "#CFA27C")],
         m=["nervous:(gyrus|lobe$|lobule|^(left |right )?insula$|white matter of cerebral hemisphere|"
            "corpus callosum|^cerebellum$|medulla oblongata|^pons$|^midbrain$)"],
         f=["brain:.*"]),
    dict(id="miyacha", uz="Miyacha", en="Cerebellum", color="#9A6048", shade="#3A1418",
         m=["nervous:^cerebellum$"], f=["brain:(cerebell)"]),
    dict(id="miya_ustuni", uz="Miya ustuni", en="Brainstem", color="#CFA36A",
         m=["nervous:^(medulla oblongata|pons|midbrain)$"],
         f=["brain:(medulla oblongata|part of pons|midbrain|cerebral peduncle)"]),
    dict(id="talamus", inside=['bosh_miya'], uz="Ko'ruv do'mbog'i (talamus)", en="Thalamus", color="#C88FC4",
         m=["nervous:^(left |right )?thalamus$"], f=["brain:(thalamus)"]),
    dict(id="gippokamp", inside=['bosh_miya'], uz="Gippokamp", en="Hippocampus", color="#7FB0D6",
         m=["nervous:^(left |right )?hippocampus$"], f=["brain:hippocamp"]),
    dict(id="orqa_miya", inside=['umurtqa', 'umurtqa_disklari'], uz="Orqa miya", en="Spinal cord", color=NERVE, m=[],
         f=["nervous:spinal cord segment|segment of cervical spinal cord"]),
    dict(id="korish_nervi", uz="Ko'ruv nervi", en="Optic nerve", color=NERVE,
         m=["nervous:optic nerve$"], f=["nervous:optic nerve"]),

    # ── Sezgi a'zolari
    dict(id="koz_olmasi", uz="Ko'z olmasi", en="Eyeball", color="#E9E4DA",
         m=["sensory:(sclera|cornea|^(left |right )?iris$|^(left |right )?lens$|vitreous body|choroid$|"
            "optic part of retina|anterior chamber of eyeball|corona ciliaris)"],
         f=["sensory:(sclera|cornea|^iris|^lens|vitreous|choroid|retina|ciliary|aqueous|pupil|macula|fovea|"
            "optic disc)"]),
    dict(id="koz_mushaklari", uz="Ko'z olmasini harakatlantiruvchi mushaklar", en="Extraocular muscles",
         color=MUSCLE, m=["muscular:^(left |right )?(superior|inferior|medial|lateral) rectus$|"
                         "^(left |right )?(superior|inferior) oblique$"],
         f=["muscular:extraocular muscle"]),
    dict(id="koz_yosh", uz="Ko'z yosh apparati", en="Lacrimal apparatus", color="#8FB8D8",
         m=["sensory:(lacrimal gland|lacrimal sac|nasolacrimal duct|lacrimal canaliculus)"], f=[]),
    dict(id="quloq_suprasi", uz="Quloq suprasi", en="External ear", color=SKIN,
         m=["sensory:external ear$"], f=[]),

    # ── Ichki sekretsiya va limfa
    dict(id="gipofiz", uz="Gipofiz", en="Pituitary gland", color="#B98ACB", m=["endocrine:pituitary"], f=[]),
    dict(id="epifiz", uz="Epifiz", en="Pineal gland", color="#B98ACB", m=["endocrine:pineal"], f=[]),
    dict(id="buyrak_usti", uz="Buyrak usti bezlari", en="Adrenal glands", color="#D9A441",
         m=["endocrine:adrenal gland"], f=[]),
    dict(id="taloq", uz="Taloq", en="Spleen", color="#6E2C4F",
         m=["lymphatic:^spleen$"], f=["lymphatic:(surface of spleen|hilum of spleen)"]),
    dict(id="ayrisimon_bez", uz="Ayrisimon bez (timus)", en="Thymus", color="#D7A7A0",
         m=["lymphatic:lobe of thymus"], f=["lymphatic:thymus lobe"]),
    dict(id="limfa_tuguni", uz="Limfa tuguni tuzilishi", en="Lymph node (structure)", color="#9FC48A", m=[],
         f=["lymphatic:(lymph node|lymphatic vessel)"]),

    # ── Teri
    dict(id="teri", uz="Teri", en="Skin (whole body surface)", color=SKIN,
         m=["integumentary:^skin$"], f=["integumentary:^skin$"]),
]

# Lotincha nom (Terminologia Anatomica): tibbiyotda a'zolar lotincha ataladi — yorliqda o'zbekcha nom ostida.
LATIN = {
    "bosh_suyagi": "Cranium", "pastki_jag": "Mandibula", "tishlar": "Dentes", "umurtqa": "Columna vertebralis",
    "umurtqa_disklari": "Disci intervertebrales", "qovurgalar": "Costae", "tosh_suyagi": "Sternum",
    "umrov": "Clavicula", "kurak": "Scapula", "yelka_suyagi": "Humerus", "bilak_suyaklari": "Radius et ulna",
    "qol_panja": "Ossa manus", "chanoq": "Pelvis", "son_suyagi": "Femur", "tizza_qopqogi": "Patella",
    "boldir_suyaklari": "Tibia et fibula", "oyoq_panja": "Ossa pedis", "skelet": "Skeleton",
    "tizza_boylamlari": "Ligamenta genus", "mushaklar": "Musculi", "diafragma": "Diaphragma",
    "kokrak_mushagi": "Musculus pectoralis major", "deltasimon": "Musculus deltoideus",
    "trapetsiyasimon": "Musculus trapezius", "qorin_mushaklari": "Musculi abdominis",
    "qovurgalararo": "Musculi intercostales", "yelka_mushaklari": "Musculi brachii",
    "dumba_mushaklari": "Musculi glutei", "son_mushaklari": "Musculi femoris", "boldir_mushaklari": "Musculi cruris",
    "yurak_bolmachalari": "Atria cordis", "yurak_qorinchalari": "Ventriculi cordis",
    "yurak_klapanlari": "Valvae cordis", "yurak": "Cor", "aorta": "Aorta",
    "aorta_yoyi": "Aorta ascendens et arcus aortae", "yuqori_kovak_vena": "Vena cava superior",
    "opka_arteriyasi": "Truncus pulmonalis", "kovak_venalar": "Venae cavae", "toj_arteriyalar": "Arteriae coronariae",
    "arteriyalar": "Arteriae", "venalar": "Venae", "hiqildoq": "Larynx", "traxeya": "Trachea", "bronxlar": "Bronchi",
    "opkalar": "Pulmones", "ong_opka": "Pulmo dexter", "chap_opka": "Pulmo sinister", "halqum": "Pharynx",
    "til": "Lingua", "solak_bezlari": "Glandulae salivariae", "qizilongach": "Oesophagus", "oshqozon": "Gaster",
    "jigar": "Hepar", "ot_pufagi": "Vesica biliaris", "ot_yollari": "Ductus biliferi", "oshqozon_osti": "Pancreas",
    "onikki_barmoq": "Duodenum", "ingichka_ichak": "Intestinum tenue", "yogon_ichak": "Intestinum crassum",
    "togri_ichak": "Rectum", "buyraklar": "Renes", "buyrak_ichki": "Medulla et calices renales",
    "siydik_naylari": "Ureteres", "siydik_pufagi": "Vesica urinaria", "siydik_kanali": "Urethra",
    "moyaklar": "Testes", "moyak_ortigi": "Epididymis", "urug_yoli": "Ductus deferens",
    "urug_pufakchalari": "Vesiculae seminales", "prostata": "Prostata", "jinsiy_olat": "Penis",
    "bachadon": "Uterus", "bachadon_boyni": "Cervix uteri", "bachadon_naylari": "Tubae uterinae",
    "tuxumdonlar": "Ovaria", "qin": "Vagina", "bachadon_boylamlari": "Ligamenta uteri", "yoldosh": "Placenta",
    "yoldosh_tomirlari": "Vasa placentae", "kindik": "Funiculus umbilicalis", "amnion": "Amnion",
    "sut_bezi": "Glandula mammaria", "bosh_miya": "Encephalon", "miyacha": "Cerebellum",
    "miya_ustuni": "Truncus encephali", "talamus": "Thalamus", "gippokamp": "Hippocampus",
    "orqa_miya": "Medulla spinalis", "korish_nervi": "Nervus opticus", "koz_olmasi": "Bulbus oculi",
    "koz_mushaklari": "Musculi bulbi", "koz_yosh": "Apparatus lacrimalis", "quloq_suprasi": "Auricula",
    "gipofiz": "Hypophysis", "epifiz": "Glandula pinealis", "buyrak_usti": "Glandulae suprarenales",
    "taloq": "Splen", "ayrisimon_bez": "Thymus", "limfa_tuguni": "Nodus lymphoideus", "teri": "Cutis",
}
for _organ in ORGANS:
    _organ["la"] = LATIN[_organ["id"]]

BY_ID = {o["id"]: o for o in ORGANS}
SOURCES = {
    "male": "BodyParts3D 4.0 (DBCLS), CC BY 4.0",
    "female": "Human Reference Atlas v1.10 (HuBMAP; NLM Visible Human), CC BY 4.0",
}
