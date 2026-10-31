# Serverni sozlash — bot qotib qolmasin, o'chsa o'zi qaytsin

2 GB li serverda xotira 100% ga chiqib, bot 40 daqiqa qotib turgan edi (disk 1 GB/s, load 10–24). Kod
tomonida endi og'ir ishlar (brauzer, LibreOffice, 3D o'girish, ONNX, PDF→Word) bitta navbatdan, bo'sh xotira
yetgandagina o'tadi (`services/heavy_gate.py`) — pik paydo bo'lmaydi, ortiqcha yuk kechikishga aylanadi.
Bu papkadagi sozlamalar — **server tomonidagi xavfsizlik to'ri**: kod kutmagan holat bo'lsa ham server
qotmaydi, bot esa o'chsa 5 soniyada o'zi qaytadi.

## Bir marta o'rnatish (5 daqiqa)

```bash
cd ~/Edu                      # loyiha papkasi
git pull
sudo bash deploy/sozlash.sh   # swap, earlyoom, systemd xizmati — botni hali to'xtatmaydi
```

Keyin mijozlar ishi tugaganini admin paneldan tekshiring («Hozir nima bajarilmoqda») va botni xizmatga
o'tkazing:

```bash
sudo bash deploy/sozlash.sh --start   # screen'dagi botni to'xtatib, systemd orqali ishga tushiradi
```

Shundan keyin `screen` kerak emas. Admin paneldagi «Yangilash» tugmasi avvalgidek ishlaydi.

## Nima o'rnatiladi

| Nima | Nima uchun |
|---|---|
| **systemd xizmati** `edufayl-bot` | Bot qaysi sabab bilan o'chsa ham (xotira, xato, server qayta yuklanishi) 5 soniyada o'zi qaytadi. Server qayta yoqilganda ham o'zi ishga tushadi. Yarim qolgan buyurtmalar puli qaytariladi, mijozga uzr xabari boradi. |
| `MemoryMax=90%`, `MemorySwapMax=512M` | Bot va uning brauzer/node jarayonlari serverning hamma xotirasini yeb, SSH'ni ham qotira olmaydi. |
| `OOMScoreAdjust=-500` + kod belgilaydi | Xotira tugasa Linux botni emas, avval brauzer, node, LibreOffice'ni o'chiradi. |
| **earlyoom** | Bo'sh xotira 5% dan kamaysa, server qotishini kutmasdan brauzer/node'ni o'chiradi. |
| **swap 1 GB**, `vm.swappiness=10` | Qisqa sakrashlarni yutadi; faqat zarurda ishlatiladi (disk "titramaydi"). |

## Kundalik buyruqlar

```bash
sudo systemctl status edufayl-bot        # ishlayaptimi
journalctl -u edufayl-bot -f             # jurnal (jonli)
journalctl -u edufayl-bot --since "1 hour ago" | grep -i -E "xotira|og'ir ish|navbat"
sudo systemctl restart edufayl-bot       # qayta ishga tushirish
journalctl -u earlyoom --since today     # earlyoom kimnidir o'chirdimi
free -m; swapon --show                   # xotira va swap
```

## Ogohlantirishlar

- **Bot o'zi xabar beradi**: bo'sh xotira 300 MB dan kamaysa (`MEMORY_ALERT_MB`) yoki diskda 2 GB dan kam joy
  qolsa (`DISK_ALERT_GB`) — adminlarga Telegram'da: nima ishlayapti, kim ko'p yeyapti. 30 daqiqada bir martadan
  ko'p takrorlanmaydi.
- **DigitalOcean**: Droplet → Monitoring → *Create alert policy* → *Memory Utilization* `> 85%` *5 min* →
  email. Xuddi shunday *Disk Utilization* `> 85%`.

## Sozlamalar (`.env`)

| O'zgaruvchi | Sukut | Ma'nosi |
|---|---|---|
| `HEAVY_PARALLEL` | 2 GB da 1, 4 GB da 2, kattasida 3 | Bir vaqtda nechta og'ir ish (brauzer, LibreOffice, 3D) |
| `HEAVY_RESERVE_MB` | 250 | Og'ir ish boshlanganda ham doim bo'sh qoladigan xotira |
| `HEAVY_BROWSER_MB`, `HEAVY_OFFICE_MB`, `HEAVY_ONNX_MB`, `HEAVY_PDF_MB`, `HEAVY_DECK3D_MB` | 450, 350, 500, 400, 400 | Har ish turining taxminiy xotirasi |
| `MEMORY_ALERT_MB` | 300 | Adminga ogohlantirish chegarasi |
| `KATALOG3D_OLDINDAN` | 0 | **2 GB serverda 0 qoldiring.** 1 — bot ishga tushganda 2000+ 3D modelni fonda o'giradi |
| `KATALOG3D_TIMEOUT` | 180 | Bitta 3D model o'girishining eng uzoq vaqti (osilib qolsa to'xtatiladi) |
| `BOT_THREADS` | 32 | Fon oqimlari soni (kutayotgan og'ir ishlar yengillarini to'sib qo'ymasin) |

## Server hajmi

1 vCPU / 2 GB — bu yuk uchun eng kichik chegara: navbat tufayli bot qotmaydi, lekin bir vaqtda ko'p buyurtma
kelsa mijozlar ko'proq kutadi (ular buni ko'rmaydi — kutish xabarida qiziqarli ma'lumotlar almashib turadi).
Buyurtmalar ko'paysa — **2 vCPU / 4 GB** droplet: `HEAVY_PARALLEL` o'zi 2 bo'ladi, kutish ikki baravar qisqaradi.
DigitalOcean'da: Droplet → Resize → CPU and RAM only (disk o'zgarmaydi, keyin qaytarish mumkin).
