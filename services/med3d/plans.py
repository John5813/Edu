"""Tayyor 3D taqdimot rejalari (namuna sifatida; keyinchalik reja AI tomonidan tuziladi)."""

DIGESTIVE_PLAN = {
    "scene": "digestive",
    "slides": [
        {"title": "Hazm qilish organlari",
         "text": "Ozuqa og'izdan to'g'ri ichakkacha bo'lgan yo'lda parchalanadi, so'riladi va qoldig'i "
                 "chiqariladi. Ushbu taqdimotda har bir organni 3D modelda ko'rib chiqamiz.",
         "show": [], "rot": [0, -25, 0]},
        {"title": "Hazm tizimining tuzilishi",
         "text": "Hazm yo'li og'iz bo'shlig'i, halqum, qizilo'ngach, oshqozon, ingichka va yo'g'on ichakdan "
                 "iborat. Jigar, o't pufagi va oshqozon osti bezi hazm shiralarini ishlab chiqarib, "
                 "jarayonga yordam beradi.",
         "show": [], "rot": [0, 0, 0],
         "labels": ["tishlar", "qizilongach", "jigar", "oshqozon", "och_ichak", "kotariluvchi", "togri_ichak"]},
        {"title": "Og'iz bo'shlig'i", "scene": "digestive_head",
         "text": "Hazm og'izda boshlanadi. Tishlar ozuqani maydalaydi, til uni aralashtiradi. So'lak bezlari "
                 "ishlab chiqargan so'lak ozuqani namlaydi, undagi amilaza fermenti kraxmalni parchalay "
                 "boshlaydi.",
         "show": ["ogiz"], "rot": [45, -20, 0],
         "labels": ["til", "tishlar", "til_osti", "jag_osti"]},
        {"title": "Qizilo'ngach",
         "text": "Qizilo'ngach — halqum bilan oshqozonni tutashtiruvchi mushakli nay. Devor mushaklarining "
                 "to'lqinsimon qisqarishi (peristaltika) ozuqa luqmasini oshqozonga suradi. Qizilo'ngachda "
                 "ozuqa hazm bo'lmaydi.",
         "show": ["qizilongach", "oshqozon"], "rot": [0, 0, 0],
         "labels": ["qizilongach", "oshqozon"]},
        {"title": "Oshqozon",
         "text": "Oshqozon devori ozuqani aralashtiradi va ezadi. Oshqozon shirasidagi xlorid kislota "
                 "mikroblarning ko'pini o'ldiradi, pepsin fermenti esa oqsillarni parchalay boshlaydi. "
                 "Ozuqa bu yerda bir necha soat qoladi.",
         "show": ["qizilongach", "oshqozon", "duodenum"], "focus": ["oshqozon"], "rot": [0, -30, 0],
         "labels": ["qizilongach", "oshqozon", "duodenum"]},
        {"title": "Jigar", "scene": "digestive_abdomen",
         "text": "Jigar — organizmdagi eng yirik bez. U o't ishlab chiqaradi, glikogen shaklida qand zaxirasini "
                 "saqlaydi va qondagi zararli moddalarni zararsizlantiradi. Uning ostida o't pufagi joylashgan.",
         "show": ["jigar", "ot", "oshqozon"], "focus": ["jigar"], "rot": [0, 0, 0],
         "labels": ["jigar", "ot_pufagi", "oshqozon"]},
        {"title": "O't pufagi va o't yo'llari", "scene": "digestive_abdomen",
         "text": "Jigarda hosil bo'lgan o't umumiy jigar yo'li va pufak yo'li orqali o't pufagiga to'planadi. "
                 "Ovqat paytida o't o'n ikki barmoq ichakka chiqadi va yog'larni mayda tomchilarga ajratadi.",
         "show": ["ot"], "rot": [0, -30, 0], "exit": "up",
         "labels": ["ot_pufagi", "pufak_yoli", "jigar_yoli"]},
        {"title": "Oshqozon osti bezi", "scene": "digestive_abdomen",
         "text": "Oshqozon osti bezi o'n ikki barmoq ichak qayrilmasida yotadi. Uning shirasidagi amilaza, "
                 "lipaza va proteazalar uglevod, yog' va oqsillarni parchalaydi. Bezning boshqa qismi insulin "
                 "va glukagon gormonlarini ishlab chiqaradi.",
         "show": ["oshqozon_osti", "duodenum"], "rot": [0, 0, 0], "exit": "up",
         "labels": ["oshqozon_osti", "duodenum"]},
        {"title": "Ingichka ichak", "scene": "digestive_abdomen",
         "text": "Ingichka ichak o'n ikki barmoq ichak, och ichak va yonbosh ichakdan iborat. Asosiy hazm va "
                 "so'rilish shu yerda bo'ladi: ichak devoridagi vorsinkalar so'rilish yuzasini ko'p marta "
                 "oshiradi.",
         "show": ["duodenum", "ingichka", "oshqozon_osti"], "focus": ["duodenum", "ingichka"], "rot": [0, 0, 0],
         "labels": ["duodenum", "och_ichak", "yonbosh_ichak"]},
        {"title": "Yo'g'on ichak", "scene": "digestive_abdomen",
         "text": "Yo'g'on ichak ingichka ichakni ramka kabi o'rab turadi. Bu yerda suv so'riladi, ichak "
                 "bakteriyalari ayrim vitaminlarni hosil qiladi. Qoldiq to'g'ri ichakda to'planadi va "
                 "tashqariga chiqariladi.",
         "show": ["yogon"], "rot": [0, 0, 0], "exit": "down",
         "labels": ["kotariluvchi", "kondalang", "tushuvchi", "appendiks", "togri_ichak"]},
        {"title": "Ozuqaning yo'li",
         "text": "Og'iz — maydalash va kraxmal hazmi.\nOshqozon — oqsillar hazmi.\nIngichka ichak — asosiy "
                 "hazm va so'rilish.\nYo'g'on ichak — suv so'rilishi.\nTo'g'ri ichak — qoldiqni chiqarish.",
         "show": [], "rot": [0, -35, 0]},
        {"title": "Xulosa",
         "text": "Hazm tizimi organlari bir-biri bilan uzviy bog'langan: biri ishdan chiqsa, butun jarayon "
                 "buziladi. Sekin chaynash, yetarli suv ichish, tolali ovqat va harakat hazm tizimini sog'lom "
                 "saqlaydi.",
         "show": [], "rot": [0, 30, 0]},
    ],
}
