"""Mijoz ismi turgan shaklning belgisi.

Taqdimot quruvchilari muqovaga ismni ("Tayyorladi: Ism") O'ZLARI qo'yadi va
o'sha matn qutisiga shu nomni beradi. Do'kon nusxasi tayyorlanganda faqat shu
nomli shakl olib tashlanadi — slaydlardagi boshqa matnga tegilmaydi.

Ilgari tozalagich ismni butun taqdimot matnidan qidirardi: "Asim" ismi
"Ponasimon" so'zida topilib, mavzu nomi bor hamma sarlavha va gap bo'shab
qolardi.
"""

AUTHOR_SHAPE = "Mijoz ismi"


def mark(shape):
    """Shaklni mijoz ismi qutisi deb belgilaydi (shaklning o'zini qaytaradi)."""
    if shape is not None:
        shape.name = AUTHOR_SHAPE
    return shape


def is_author(shape) -> bool:
    return getattr(shape, "name", "") == AUTHOR_SHAPE
