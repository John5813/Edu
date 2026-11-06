"""Katalog modellarini toifalarga (kategoriya) ajratish: `kategoriya` maydonini yozadi.

    python tools/katalog3d/toifalash.py            # katalog.json ni yangilaydi
    python tools/katalog3d/toifalash.py --boshqa   # faqat «Boshqa» ga tushganlarni chiqaradi (qoidani to'ldirish uchun)

Toifa model nomi (asl va o'zbekcha) hamda teglari bo'yicha qoidalar ro'yxatidan aniqlanadi — birinchi mos kelgani
olinadi, shuning uchun tartib muhim (aniqrog'i yuqorida). Hech biri mos kelmasa — `fan` bo'yicha zaxira toifa.
Bolalar katalogi (`bolalar.json`) o'z toifalarini olgan: ularga teginilmaydi.

`kategoriya` qidiruvda ishlatiladi (`services/kat3d/qidiruv.py`): mavzu toifasiga mos modellar ball oladi va
AI tanlovi uchun nomzodlar toifa bo'yicha guruhlanadi.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KATALOG = os.path.join(ROOT, "data", "katalog3d", "katalog.json")

# Har fan ichida: (toifa, regex) — birinchi mos kelgani olinadi, shuning uchun tartib muhim. Faqat nom (asl va
# o'zbekcha) tekshiriladi (teglar chalg'itadi). Fan — avvalgi saralashda AI bergan, ishonchli asos.
UZ = (r"samarkand|samarqand|shahrisabz|shakhrisabz|bukhara|buxoro|uzbek|o'zbek|registan|registon|teshik-?tash|teshiktosh|"
      r"timor|timur|temur|ulugh beg|ulug'bek|oftoba|bibi-?khanym|bibixonim|gūr-i|go'ri amir")
BIO = [
    ("Dinozavrlar va qazilma hayvonlar", r"saur|dinosaur|dinozavr|tyrannosaur|triceratops|raptor|pteranodon|megalodon|mamont|"
                                          r"mammoth|mastodon|smilodon|fossil|qazilma|trilobit|ammonit|qadimgi|archaeopteryx|"
                                          r"arxeopteriks|diplokaulus|diplocaulus|eremoterium|uintateriy|oreodont|desmostil"),
    ("Skeletlar va bosh suyaklari", r"skull|skeleton|skelet|bosh suyag|cranium|jag'|\bjaw|humerus|yelka suyag|vertebra|umurtqa|"
                                    r"\bantler|shoxi\b|\bhorn\b|\btusk|fil tishi|suyag"),
    ("Dengiz umurtqasizlari", r"coral|marjon|shell|chig'anoq|starfish|dengiz yulduzi|sponge|gubka|\bcrab|krab|lobster|omar|"
                              r"shrimp|krevetka|bryozo|mshanka|urchin|tipratikan|barnacle|balanus|mussel|midiya|oyster|"
                              r"ikki pallali|nautilus|octopus|sakkizoyoq|jellyfish|meduza|crinoid|nilufari|isopod|izopod|"
                              r"horseshoe|taqasimon|qisqichbaqa|shilliqqurt|\bsnail|squid|kalmar|\bmurex"),
    ("Baliqlar va dengiz sutemizuvchilari", r"\bfish|baliq|shark|akula|whale|\bkit\b|dolphin|delfin|\bseal\b|tyulen|sea lion|"
                                           r"dengiz sheri|sea otter|dengiz susari|piranh|\beel\b|ilonbaliq|sturgeon|osetr|"
                                           r"\bbass\b|okun|barrakuda|barracuda|seahorse|dengiz oti|kosatka|walrus|morj|grinda"),
    ("Qushlar", r"\bbird|qush|\bowl|boyo'?gli|eagle|burgut|vulture|kalxat|penguin|pingvin|swan|oqqush|\bduck|o'rdak|"
                r"hummingbird|kolibri|pelican|birqozon|raven|qarg'a|dove|kaptar|hornbill|shoxtumshuq|tanager|godwit|"
                r"loyxo'rak|spoonbill|qoshiqtumshuq|\bemu\b|\bgoose|g'oz|shelduck|peganka|sparrow|chittak|bunting|"
                r"suli qushi|kenguru qush"),
    ("Sudralib yuruvchilar va amfibiyalar", r"lizard|kaltakesak|gecko|gekkon|turtle|tortoise|toshbaqa|\bsnake|\bilon\b|python|"
                                           r"piton|cobra|kobra|crocodile|alligator|caiman|kayman|timsoh|\bfrog|qurbaqa|iguana|"
                                           r"chameleon|xameleon|agama|tuatara|amphibian|\btoad|\bboa\b|bo'g'ma|rana\b"),
    ("Hasharotlar va o'rgimchaklar", r"insect|hasharot|beetle|qo'ng'iz|butterfly|kapalak|\bbee\b|asalari|bumble|bombus|"
                                     r"\bant\b|chumoli|wasp|hornet|shoxari|spider|o'rgimchak|grasshopper|chigirtka|cockroach|"
                                     r"suvarak|ladybug|xonqizi|\bfly\b|pashsha|cicada|sikada|qandala|\bbug\b|dragonfly|"
                                     r"\bari\b|sirfid|tarantula|midge|tetragnat|kolorado"),
    ("Tibbiyot va anatomiya", r"\bdna\b|dnk|\bhuman\b|\bodam\b|\bbrain|miya|anatom"),
    ("Qo'ziqorinlar", r"mushroom|qo'ziqorin|amanita|mux'?omor|fungus|toadstool"),
    ("Meva, sabzavot va ekinlar", r"\bapple|olma|banan|pineapple|ananas|pomegranate|anor|avocado|avokado|cucumber|bodring|"
                                  r"carrot|sabzi|potato|kartoshka|onion|piyoz|garlic|sarimsoq|cabbage|karam|\bcorn|makkajo|"
                                  r"wheat|bug'doy|pumpkin|qovoq|gourd|strawberry|qulupnay|berr|rezavor|watermelon|tarvuz|"
                                  r"walnut|yong'oq|papay|coffee bean|qahva don|lemon|limon|artichoke|artishok|parsnip|"
                                  r"pasternak|fruit|meva|vegetable|sabzavot|pepper|qalampir|salad|salat|cucumber|"
                                  r"kokos|coconut|nuts|sprouted|mango|grape|uzum|peach|shaftoli"),
    ("Daraxtlar va to'nkalar", r"\btree|daraxt|stump|to'nka|trunk|\blogs?\b|g'o'la|\bbush|buta|\bpalm|palma|\boak|eman|"
                               r"\bpine|qarag'ay|spruce|\barcha\b|forest|o'rmon|\broots?\b|ildiz|branch|shox\b|redwood|sekvoya|"
                               r"bamboo|bambuk|banyan|\bfig\b|anjir|olive|zaytun|acacia|akatsiya|chestnut|kashtan|chinor|"
                               r"hornbeam|grab daraxt|pohutukawa|poxutukava|deadwood|moss"),
    ("Gullar va o'simliklar", r"flower|\bgul\b|gullar|\brose|atirgul|tulip|lola|dais|moychechak|orchid|orxideya|cact|kaktus|"
                              r"fern|qirqquloq|succulent|sukkulent|plant|o'simlik|aloe|begonia|hibiscus|gibiskus|sunflower|"
                              r"kungaboqar|azalea|wisteria|clover|sebarga|grass|o't\b|\bleaf|barg|petunia|chrysanth|xrizantema|"
                              r"hydrangea|gortenziya|ficus|fikus|dracena|hoya|xoya|haworthia|blossom|sakura|cherry|gilos|"
                              r"anthurium|anturium|lamium|yasnotka|ornithogalum|ornitogalum|weigela|vaygela|bellis|hay bales|"
                              r"pichan|vase and flowers|guldondagi"),
]
MAMMAL = (r"elephant|\bfil\b|giraffe|jirafa|\blion|\bsher\b|tiger|yo'lbars|\bbear|ayiq|wolf|bo'ri|\bfox|tulki|deer|"
          r"bug'u|\bhorse|\bot\b|camel|tuya|rhino|karkidon|hippo|begemot|zebra|panda|monkey|maymun|gorilla|chimpanzee|"
          r"shimpanze|kangaroo|kenguru|bison|bizon|zubr|\bsheep|qo'y\b|\bgoat|echki|\bcow\b|sigir|\bbull|buqa|\bpig\b|"
          r"cho'chqa|\bboar|\bdog|\bit\b|\bcat\b|mushuk|rabbit|quyon|mouse|sichqon|shrew|shrev|\bmole|ko'rsichqon|"
          r"ferret|xorek|lynx|silovsin|\bbat\b|antelope|antilopa|alpaca|alpaka|moose|\blos\b|bulan|mammal|lemur|sloth|"
          r"yalqov|echidna|exidna|coyote|koyot|baboon|babuin|tamarin|buffalo|buyvol|bighorn|pinsher|pinscher|elik|roe|"
          r"lan bug'u|dormouse|uyquchi|marmot|gopher|squirrel|olmaxon|hedgehog|tipratikan\b")

ARCH = [
    ("O'zbekiston yodgorliklari", UZ),
    ("Qal'alar va istehkomlar", r"castle|qal'a|\bfort\b|fortress|château|chateau|bastion|citadel|great wall|devor|gatehouse"),
    ("Ibodatxonalar va cherkovlar", r"cathedral|sobor|church|cherkov|chapel|ibodatxona|temple|mosque|masjid|shrine|monastery|"
                                    r"monastir|abbey|abbat|priory|synagogue|sinagoga|pagoda|basilica|kirche|kościół|stavkirke|"
                                    r"minster|mehrob|altarpiece|vitraj|stained glass|cloister|ayvon|ermita|ermitaj|"
                                    r"catholic|rose window|atirgul deraza|gotik"),
    ("Ko'priklar, favvoralar va yodgorliklar", r"bridge|ko'prik|fountain|favvora|monument|yodgorlik|\barch\b|\bark\b|arka|"
                                               r"\bgate\b|darvoza|column|ustun|memorial|obelisk|dolmen|tomb|qabr|stonehenge|"
                                               r"runestone|cairn|\bwell\b|quduq|lighthouse|mayoq|pyramid|piramida|statue of liberty|"
                                               r"ozodlik haykali|torii|walkway|ravoq|portal|steps|zina"),
]
ARCH_DEFAULT = "Binolar, uylar va saroylar"

TRANSPORT = [
    ("Mototsikl, velosiped va skuterlar", r"motorcycle|motorbike|mototsikl|scooter|skuter|moped|vespa|bicycle|velosiped|"
                                          r"\bbike\b|bmx|ducati|cafe racer|kafe-reyser|indian chief|honda nr|nr750|\bnsx|hobbit|"
                                          r"kiwi|xdiavel"),
    ("Poyezdlar va temir yo'l", r"\btrain|poyezd|locomotive|lokomotiv|parovoz|\brail|tram\b|tramvay|metro|subway|wagon|vagon|"
                                r"class \d+|intercity|depot|vokzal|elektrovoz|railroad|station|pullman|mark 3|car type"),
    ("Samolyot, vertolyot va kosmik texnika", r"plane\b|airplane|aircraft|samolyot|helicopter|vertolyot|boeing|douglas|dc-?3|"
                                              r"airliner|bomber|biplane|zeppelin|tsepellin|airship|dirijabl|\bdrone|\bdron|flyer|"
                                              r"antonov|an-\d|il-76|ilyushin|yakovlev|yak-40|cirrus|bell x|dornier|westland|"
                                              r"latec|latékoer|hydroplane|gidrosamolyot|wright|rayt"),
    ("Kemalar va qayiqlar", r"\bship\b|\bboat|qayiq|kema|vessel|yacht|submarine|suv osti|tanker|ferry|steamboat|\bcanoe|"
                            r"kayak|longboat|\bbarge|\bskiff|wreck|cargo ship|container ship|\bliner|\bmv\b|\bsy\b|rnlb|"
                            r"gabarra|pram|dubas|punt"),
    ("Yuk transporti va maxsus texnika", r"truck|yuk mashina|tractor|traktor|excavator|ekskavator|bulldozer|loader|yuklagich|"
                                         r"forklift|\bcrane|kran|cement mixer|beton|grader|greyder|roller|katok|container|konteyner|"
                                         r"trailer|tirkama|tyagach|semi\b|pallet|palet|mining|samosval|\bbus\b|avtobus|ambulance|"
                                         r"tanker|signal|svetofor|road sign|yo'l belgi|tyre|tire|shina|wheel|g'ildirak|"
                                         r"catering|furgon|\bvan\b|kenworth|scania|daf |volvo fh|freightliner|paz|suzuki carry"),
]
TRANSPORT_DEFAULT = "Avtomobillar"

TEXNIKA = [
    ("Yuk transporti va maxsus texnika", r"truck|samosval|tractor|traktor|excavator|ekskavator|forklift|yuklagich|loader|crane|"
                                         r"kran|grader|greyder|roller|katok|cement|beton|pallet|palet|conveyor|konveyer|"
                                         r"escalator|eskalator|boxes|qutilar|tanks|rezervuar"),
    ("Soatlar va o'lchov asboblari", r"clock|watch|\bsoat|budilnik|alarm|scale|tarozi|compass|kompas|sextant|sekstant|"
                                     r"hourglass|qum soati|heliograph|geliograf|microscope|mikroskop|binocular|durbin"),
    ("Kompyuter va elektronika", r"computer|kompyuter|laptop|noutbuk|keyboard|klaviatura|monitor|sichqoncha|motherboard|"
                                 r"raspberry|iphone|galaxy s|phone|telefon|\btv\b|televizor|television|radio|camera|"
                                 r"fotoapparat|kamera|kinokamera|speaker|karnay|headphone|disk|\bssd|\bhdd|printer|server|"
                                 r"cassette|kassetali|recorder|magnitofon|walkman|\bvcr|\bvhs|calculator|hisoblash|"
                                 r"\bibm|commodore|transistor|circuit|microchip|tablet|planshet|crt|kineskop|\bdron"),
    ("Fizika va elektr", r"electric|elektr|battery|batareya|generator|turbine|turbina|bulb|lampochka|telegraph|"
                                   r"telegraf|oscillo|ossillo|galvanometer|coil|g'altak|transformer|kuchlanish|voltage|"
                                   r"microscope|mikroskop|stereoscope|stereoskop|sextant|sekstant|compass|kompas|scale|"
                                   r"tarozi|balance|hourglass|qum soati|heliograph|geliograf|binocular|durbin|antenna|relay|"
                                   r"rele|signal generator|plug|vilka"),
]
TEXNIKA_DEFAULT = "Mashinalar, asboblar va maishiy texnika"


FAN_TOIFA = {
    "astronomiya": "Sayyoralar va koinot", "geografiya": "Tog'lar, qoyalar va relyef", "oshxona": "Taom va oshxona",
    "fizika": "Fizika va elektr", "informatika": "Kompyuter va elektronika", "musiqa": "Musiqa asboblari",
    "tibbiyot": "Tibbiyot va anatomiya", "sport": "Sport", "kimyo": "Fizika va elektr",
    "adabiyot": "Binolar, uylar va saroylar", "matematika": "Fizika va elektr",
}

_IDISH = (r"vessel|idish|\bvase|vaza|guldon|\bpot\b|tuvak|\bjar\b|\bjug\b|ko'za|ewer|\bbowl|kosa|krater|kylix|kiliks|"
          r"\bhydria|gidriya|stein|krujka|bucket|chelak|canteen|\bcup\b|piyola|lebes|aryballos|ariballos|\bcopa\b|"
          r"bottle|shisha|\bbox\b|quti|\btin\b|ashtray|kuldon|burner|tutatqi|besamim")
_MEBEL = (r"\btable|\bstol\b|chair|stul|\bdesk|dresser|komod|\bchest|sandiq|cabinet|shkaf|kreslo|armchair|\bbench|"
          r"o'rindiq|stove|pech|lamp|chiroq|candle|\bsham\b|shamdon|chandelier|qandil|\bclock|\bsoat|\bkey\b|kalit|"
          r"basket|savat|\bcart\b|arava|wagon|carriage|karet|sink|rakovina|samovar|handbag|sumka|birdcage|qafas|parasol|"
          r"soyabon|knocker|taqillat|cash box|pul qutisi|opener|ochqich|binocular|durbin|knob|tugma")
_KITOB = r"\bbook|kitob|manuscript|qo'lyozma|scroll|o'ram|album|\bms \d|pentateuch|tavrot|menak|declaration"
_SHAXS = (r"lincoln|linkoln|jackson|jekson|washington|vashington|roosevelt|ruzvelt|garfield|garfild|hayes|xeyz|keller|"
          r"theodore|rutherford|endryu|jorj|helen")
TARIX_DEFAULT = "Tarixiy buyumlar va yodgorliklar"

TARIX = [
    ("Niqoblar", r"\bmask|niqob"),
    ("Kiyim-kechak va poyabzal", r"dress|ko'ylak|skirt|yubka|kimono|\bhat\b|shlyapa|helmet|dubulg'a|jersey|robe|chakmon|"
                                 r"blouse|bluzka|\bsuit|kostyum|\bshoe|poyabzal|sneaker|krossovka|boot|botinka|apron|fartuk|"
                                 r"costume|clothes|kiyim|slipper|shippak|corset|korset|bracelet|bilaguzuk|jewel|zargarlik|"
                                 r"hairpin|to'g'nag'ich|bicorn|bikorn|armadura|zirh|armor|samuray"),
    ("Qal'alar va istehkomlar", ARCH[1][1]),
    ("Ibodatxonalar va cherkovlar", ARCH[2][1]),
    ("Ko'priklar, favvoralar va yodgorliklar", ARCH[3][1]),
    ("Haykallar va byustlar", r"statue|haykal|sculpture|\bbust|byust|relief|barelyef|figura|statuette|netsuke|buddha|budda|"
                              r"angel|farishta|cupid|kupidon|gargoyle|gargulya|totem|lamassu|sphinx|sfinks|athena|afina|zeus|"
                              r"hermes|gerakl|venus|venera|goddess|ma'buda|\bhead\b|boshi\b|bodhisattva|bodxisattva|arhat|"
                              r"arxat|guanyin|ganesh|shiva|tiki|effigy|nefertiti|king\b|qiroli|ram of|qo'chqori|baboon|babuin|"
                              r"scarab|skarabey|cat\b|mushugi|hippo|begemot|lion|sher"),
    ("Binolar, uylar va saroylar", r"palace|saroy|\bhouse|\buy\b|building|bino|\bhall\b|zal\b|library|kutubxona|museum|"
                                   r"facade|fasad|tower|minora|barn|ombor|cabin|kulba|hotel|market|bozor|school|maktab|farm|"
                                   r"\bmill\b|tegirmon|village|qishloq|stable|otxona|granary|windmill|villa|ruin|xarob|"
                                   r"caves|g'or\b|catacomb|katakomb|baths?\b|hammom|theat|teatr|observatory|kamin|fireplace|"
                                   r"chimney|mo'ri|temple|karst|nuragic|settlement"),
    ("Musiqa asboblari", r"piano|guitar|violin|drum|trumpet|saxophone|sitar|instrument|cholg'u|\bbell\b|qo'ng'iroq|xylophone"),
    ("Tarixiy shaxslar", _SHAXS),
    ("Kitoblar va qo'lyozmalar", _KITOB),
    ("Idishlar va ko'zalar", _IDISH),
    ("Mebel va uy-ro'zg'or buyumlari", _MEBEL),
]


SANAT = [
    ("Niqoblar", r"\bmask|niqob"),
    ("Kiyim-kechak va poyabzal", TARIX[1][1]),
    ("Idishlar va ko'zalar", _IDISH),
    ("Mebel va uy-ro'zg'or buyumlari", _MEBEL),
    ("Haykallar va byustlar", r"haykal|statue|sculpture|bust|byust|figure|relief|barelyef|fountain|favvora|louvre|luvr|"
                              r"netsuke|angel|farishta|cupid|kupidon|goddess|ma'buda|head\b|boshi\b|lion|sher\b|horse|\bot\b|"
                              r"bull|buqa|dancer|raqq|faun|satyr|muse|muza|nymph|apostle|havoriy|christ|madonna|pieta|pyeta|"
                              r"hebe|geba|aphrodite|afrodita|venus|venera|diana|apollo|hercule|gerakl|eros|psyche|psixeya|"
                              r"stag|bear|ayiq|stork|laylak|swan|oqqush|owl|boyo'g|eagle|burgut|dog|\bit\b|elephant|fil\b|"
                              r"ox\b|ho'kiz|kitsune|komainu|crocodile|timsoh|frog|qurbaqa|sphinx|sfinks"),
]
SANAT_DEFAULT = "San'at buyumlari"
def _rx(rows):
    return [(name, re.compile(rx, re.IGNORECASE)) for name, rx in rows]


_BIO, _ARCH, _TRANSPORT, _TEXNIKA, _TARIX, _SANAT = map(_rx, (BIO, ARCH, TRANSPORT, TEXNIKA, TARIX, SANAT))
_MAMMAL = re.compile(MAMMAL, re.IGNORECASE)
_UZ = re.compile(UZ, re.IGNORECASE)


def _first(rules, text):
    for name, rx in rules:
        if rx.search(text):
            return name
    return None


def toifa(m: dict) -> str:
    """Model toifasi: avval O'zbekiston yodgorliklari, keyin fan bo'yicha qoidalar (nom bo'yicha)."""
    text = " ".join([m.get("nom", ""), m.get("nom_uz", "")])
    fan = m.get("fan")
    if _UZ.search(text):
        return "O'zbekiston yodgorliklari"
    if fan == "biologiya":
        found = _first(_BIO, text)
        if found:
            return found
        return "Sutemizuvchilar" if _MAMMAL.search(text) else "Boshqa tabiat obyektlari"
    if fan == "arxitektura":
        return _first(_ARCH[1:], text) or ARCH_DEFAULT
    if fan == "transport":
        return _first(_TRANSPORT, text) or TRANSPORT_DEFAULT
    if fan == "texnika":
        return _first(_TEXNIKA, text) or TEXNIKA_DEFAULT
    if fan == "tarix":
        return _first(_TARIX, text) or TARIX_DEFAULT
    if fan == "san'at":
        return _first(_SANAT, text) or SANAT_DEFAULT
    return FAN_TOIFA.get(fan, "Boshqa")


def main():
    with open(KATALOG, encoding="utf-8") as fh:
        data = json.load(fh)
    stat = {}
    boshqa = []
    for m in data["modellar"]:
        m["kategoriya"] = toifa(m)
        m.setdefault("tur", "real")
        stat[m["kategoriya"]] = stat.get(m["kategoriya"], 0) + 1
        if m["kategoriya"] in ("Boshqa", "Boshqa tabiat obyektlari", TARIX_DEFAULT, SANAT_DEFAULT, TEXNIKA_DEFAULT):
            boshqa.append(m)
    if "--boshqa" in sys.argv:
        for m in boshqa:
            print(m["id"][:8], m["fan"], "|", m["nom"][:45], "|", m["nom_uz"][:45])
        return
    for k, v in sorted(stat.items(), key=lambda kv: -kv[1]):
        print(f"{v:5d}  {k}")
    with open(KATALOG, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
