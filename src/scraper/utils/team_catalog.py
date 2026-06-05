"""
Универсальный каталог сущностей (сборные, клубы, игроки).

Правило: один canonical key + display на английском; все локальные написания
(RO/RU/AR/… и опечатки парсера) — в names → mechanical_key → alias.

Новый источник на любом языке: canonical_team_key(raw) → england;
display → England; raw ≠ English → teams.aliases.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    key: str
    display: str
    names: tuple[str, ...]


def _e(key: str, display: str, *local: str) -> CatalogEntry:
    """display всегда в names; local — любые языки и транслит."""
    return CatalogEntry(key, display, (display, *local))


# fmt: off
COUNTRY_CATALOG: tuple[CatalogEntry, ...] = (
    _e("england", "England", "Anglia", "Англия", "Angleterre", "Inglaterra", "إنجلترا"),
    _e("france", "France", "Franta", "Franța", "Франция", "Frantsiya", "Franciya", "فرنسا"),
    _e("germany", "Germany", "Germania", "Германия", "Germaniya", "Deutschland", "ألمانيا"),
    _e("spain", "Spain", "Spania", "Испания", "Ispaniya", "España", "إسبانيا"),
    _e("italy", "Italy", "Italia", "Италия", "إيطاليا"),
    _e("portugal", "Portugal", "Portugalia", "Portugaliya", "Португалия", "البرتغال"),
    _e("netherlands", "Netherlands", "Olanda", "Tarile de jos", "Țările de Jos", "Нидерланды", "Niderlandy", "Holland", "هولندا"),
    _e("belgium", "Belgium", "Belgia", "Бельгия", "Belgiya", "بلجيكا"),
    _e("denmark", "Denmark", "Danemarca", "Дания", "الدنمارك"),
    _e("sweden", "Sweden", "Suedia", "Швеция", "Shvetsiya", "السويد"),
    _e("norway", "Norway", "Norvegia", "Норвегия", "النرويج"),
    _e("finland", "Finland", "Finlanda", "Финляндия", "Finlyandiya", "فنلندا"),
    _e("poland", "Poland", "Polonia", "Польша", "بولندا"),
    _e("czechia", "Czechia", "Czech Republic", "Chehiya", "Chekhiya", "Чехия", "التشيك"),
    _e("slovakia", "Slovakia", "Slovacia", "Slovakiya", "Словакия", "سلوفاكيا"),
    _e("slovenia", "Slovenia", "Sloveniya", "Словения", "سلوفينيا"),
    _e("hungary", "Hungary", "Ungaria", "Венгрия", "Vengriya", "المجر"),
    _e("romania", "Romania", "România", "Румыния", "Rumyniya", "رومانيا"),
    _e("bulgaria", "Bulgaria", "Болгария", "Bolgariya", "بلغاريا"),
    _e("greece", "Greece", "Grecia", "Греция", "Gretsiya", "اليونان"),
    _e("turkey", "Turkey", "Turcia", "Turtsiya", "Турция", "تركيا"),
    _e("ukraine", "Ukraine", "Ucraina", "Украина", "أوكرانيا"),
    _e("russia", "Russia", "Rusia", "Rossiya", "Rossiia", "Россия", "روسيا"),
    _e("belarus", "Belarus", "Беларусь", "بيلاروسيا"),
    _e("moldova", "Moldova", "Молдова", "مولدوفا"),
    _e("serbia", "Serbia", "Serbiya", "Сербия", "صربيا"),
    _e("montenegro", "Montenegro", "Muntenegru", "Черногория", "الجبل الأسود"),
    _e("bosnia", "Bosnia and Herzegovina", "Bosnia", "Босния и Герцеговина", "Bosniya i Gertsegovina", "البوسنة"),
    _e("croatia", "Croatia", "Croația", "Хорватия", "كرواتيا"),
    _e("albania", "Albania", "Албания", "ألبانيا"),
    _e("northmacedonia", "North Macedonia", "Macedonia", "Македония"),
    _e("kosovo", "Kosovo", "Косово"),
    _e("austria", "Austria", "Австрия", "النمسا"),
    _e("switzerland", "Switzerland", "Elveția", "Elvetia", "Швейцария", "Shveitsariya", "Shveytsariya", "سويسرا"),
    _e("ireland", "Ireland", "Irlanda", "Ирландия", "Irlandiya", "أيرلندا"),
    _e("northernireland", "Northern Ireland", "Severnaya Irlandiya", "إيرلندا الشمالية"),
    _e("scotland", "Scotland", "Scoția", "Шотландия", "اسكتلندا"),
    _e("wales", "Wales", "Tara Galilor", "Țara Galilor", "Уэльс", "Uels", "ويلز"),
    _e("luxembourg", "Luxembourg", "Luxemburg", "Люксембург"),
    _e("andorra", "Andorra", "Андорра"),
    _e("liechtenstein", "Liechtenstein", "Lihtenshtein", "Лихтенштейн"),
    _e("sanmarino", "San Marino", "Sanmarino", "Сан Марино"),
    _e("malta", "Malta", "Мальта", "مالطا"),
    _e("cyprus", "Cyprus", "Kipr", "Кипр", "قبرص"),
    _e("iceland", "Iceland", "Islanda", "Исландия"),

    _e("usa", "USA", "SUA", "США", "SSHA", "United States", "الولايات المتحدة"),
    _e("canada", "Canada", "Kanada", "Канада", "كندا"),
    _e("mexico", "Mexico", "Mexic", "Meksika", "Мексика", "المكسيك"),
    _e("brazil", "Brazil", "Brazilia", "Braziliya", "Braziliei", "Бразилия", "البرازيل"),
    _e("argentina", "Argentina", "Аргентина", "الأرجنتين"),
    _e("colombia", "Colombia", "Columbia", "Колумбия", "كولومبيا"),
    _e("chile", "Chile", "Chili", "Чили", "تشيلي"),
    _e("venezuela", "Venezuela", "Венесуэла", "فنزويلا"),
    _e("ecuador", "Ecuador", "Эквадор"),
    _e("peru", "Peru", "Перу"),
    _e("uruguay", "Uruguay", "Уругвай"),
    _e("paraguay", "Paraguay", "Парагвай"),
    _e("bolivia", "Bolivia", "Боливия"),
    _e("honduras", "Honduras", "Гондурас"),
    _e("costarica", "Costa Rica", "Коста-Рика"),
    _e("panama", "Panama", "Панама"),
    _e("jamaica", "Jamaica", "Ямайка"),
    _e("dominican", "Dominican Republic", "Dominikana", "Republicii Dominicane", "Доминикана"),

    _e("australia", "Australia", "Avstraliya", "Австралия", "أستراليا"),
    _e("newzealand", "New Zealand", "Noua Zeelanda", "Noua Zelanda", "Новая Зеландия", "Novaya Zelandiya", "نيوزيلندا"),
    _e("japan", "Japan", "Japonia", "Япония", "اليابان"),
    _e("southkorea", "South Korea", "Korea Republic", "Yuzhnaya Koreya", "Yuzhnaya Korei", "Южная Корея", "كوريا الجنوبية"),
    _e("china", "China", "Kitai", "Китай", "الصين"),
    _e("india", "India", "Indiya", "Индия", "الهند"),
    _e("indonesia", "Indonesia", "Indoneziya", "Индонезия"),
    _e("thailand", "Thailand", "Tailand", "Таиланд", "تايلاند"),
    _e("vietnam", "Vietnam", "Вьетнам"),
    _e("singapore", "Singapore", "Singapur", "Сингапур"),
    _e("malaysia", "Malaysia", "Малайзия"),
    _e("philippines", "Philippines", "Филиппины"),
    _e("uzbekistan", "Uzbekistan", "Узбекистан", "أوزبكستان"),
    _e("kazakhstan", "Kazakhstan", "Kazahstan", "Казахстан", "كازاخستان"),
    _e("tajikistan", "Tajikistan", "Tadzhikistan", "Таджикистан"),
    _e("kyrgyzstan", "Kyrgyzstan", "Кыргызстан"),
    _e("turkmenistan", "Turkmenistan", "Туркменистан"),
    _e("armenia", "Armenia", "Armeniya", "Армения", "أرمينيا"),
    _e("azerbaijan", "Azerbaijan", "Azerbaidzhan", "Азербайджан"),
    _e("georgia", "Georgia", "Грузия"),
    _e("iran", "Iran", "Иран", "إيران"),
    _e("iraq", "Iraq", "Irak", "Ирак", "العراق"),
    _e("syria", "Syria", "Siriya", "Сирия", "سوريا"),
    _e("saudiarabia", "Saudi Arabia", "Arabia Saudita", "Саудовская Аравия", "السعودية"),
    _e("uae", "UAE", "Emiratele Arabe Unite", "ОАЭ"),
    _e("qatar", "Qatar", "Катар", "قطر"),
    _e("kuwait", "Kuwait", "Kuveit", "الكويت"),
    _e("oman", "Oman", "Оман", "عمان"),
    _e("jordan", "Jordan", "Iordania", "Иордания", "الأردن"),
    _e("lebanon", "Lebanon", "Ливан", "لبنان"),
    _e("israel", "Israel", "Израиль", "إسرائيل"),
    _e("palestine", "Palestine", "Палестина", "فلسطين"),

    _e("egypt", "Egypt", "Egipt", "Египет", "مصر"),
    _e("morocco", "Morocco", "Maroc", "Марокко", "المغرب"),
    _e("algeria", "Algeria", "Alger", "Алжир", "الجزائر"),
    _e("tunisia", "Tunisia", "Tunis", "Тунис", "تونس"),
    _e("nigeria", "Nigeria", "Нигерия", "نيجيريا"),
    _e("senegal", "Senegal", "Сенегал"),
    _e("ghana", "Ghana", "Гана"),
    _e("cameroon", "Cameroon", "Камерун"),
    _e("ivorycoast", "Ivory Coast", "Coasta de Fildes", "Coasta de Fildeș", "Кот-д'Ивуар", "Kot divuar", "Cote d'Ivoire", "ساحل العاج"),
    _e("drcongo", "DR Congo", "Congo DR", "ДР Конго"),
    _e("congo", "Congo", "Конго"),
    _e("southafrica", "South Africa", "Africa de Sud", "ЮАР"),
    _e("guinea", "Guinea", "Gvinea", "Гвинея", "غينيا"),
    _e("guatemala", "Guatemala", "Gvatemala", "Гватемала"),

    _e("brazilwomen", "Brazil (W)", "Brazilia (F)", "Braziliei (F)", "Бразилия (жен.)", "Бразилия (жен)"),
    _e("dominicanwomen", "Dominican Republic (W)", "Dominikana (жен)", "Republicii Dominicane (F)"),
    _e("turkeywomen", "Turkey (W)", "Turtsiya (zhen)", "Турция (жен.)"),
    _e("netherlandswomen", "Netherlands (W)", "Niderlandy (zhen)", "Niderlandy (жен)", "Tarile de jos (F)"),

    _e("cska", "CSKA", "TSSKA", "ЦСКА"),
    _e("unics", "UNICS", "Uniks", "УНИКС"),
    _e("indianafever", "Indiana Fever", "Indiana Fiver"),
    _e("atlantadream", "Atlanta Dream", "Atlanta Drim"),
    _e("knicksnewyork", "New York Knicks", "New York Knicks"),
    _e(
        "antoniosanspurs",
        "San Antonio Spurs",
        "San Antonio Spurs",
        "Сан-Антонио Сперз",
        "Сан Антонио Сперз",
    ),
    _e(
        "clubmontevideoracing",
        "Racing Club Montevideo",
        "Racing Club Montevideo",
        "Расинг Клуб Монтевидео",
    ),
)
# fmt: on

# mechanical_key → canonical (сокращения, старые ключи БД, теннис)
EXTRA_ALIASES: dict[str, str] = {
    "frana": "france",
    "franciyakot": "france",
    "coastadefildes": "ivorycoast",
    "coastadefilde": "ivorycoast",
    "coastadefildei": "ivorycoast",
    "kotdivuar": "ivorycoast",
    "kotdivoire": "ivorycoast",
    "cotedivoire": "ivorycoast",
    "divuar": "ivorycoast",
    "taragalilor": "wales",
    "tariledejos": "netherlands",
    "czechrepublic": "czechia",
    "severnayairlandiya": "northernireland",
    "republiciidominicane": "dominican",
    "republiciidominicana": "dominican",
    "koreyayuzhnaya": "southkorea",
    "braziliyazhen": "brazilwomen",
    "braziliyawomen": "brazilwomen",
    "brazilief": "brazilwomen",
    "dominikanazhen": "dominicanwomen",
    "dominikanawomen": "dominicanwomen",
    "republiciidominicanef": "dominicanwomen",
    "dominicanerepubliciiwomen": "dominicanwomen",
    "dominicanrepublicwomen": "dominicanwomen",
    "turtsiyazhen": "turkeywomen",
    "turtsiyawomen": "turkeywomen",
    "niderlandyzhen": "netherlandswomen",
    "niderlandywomen": "netherlandswomen",
    "tariledejoswomen": "netherlandswomen",
    "arnaldim": "arnaldimatteo",
    "matteoarnaldi": "arnaldimatteo",
    "kobollif": "cobolliflavio",
    "flaviocobolli": "cobolliflavio",
    "flaviokobolli": "cobolliflavio",
    "flaviokoboli": "cobolliflavio",
    "menshikya": "mensikjakub",
    "jakubmensik": "mensikjakub",
    "yakubmenshik": "mensikjakub",
    "yakubmensik": "mensikjakub",
    "zvereva": "zverevalexander",
    "alexanderzverev": "zverevalexander",
    "aleksandrzverev": "zverevalexander",
    "aleksanderzverev": "zverevalexander",
    "shnaiderd": "shnaiderdiana",
    "dianashnaider": "shnaiderdiana",
    "hvalinskam": "chwalinskamaja",
    "majachwalinska": "chwalinskamaja",
    "kostyukm": "kostyukmarta",
    "andreevam": "andreevamirra",
    "sanantoniosperz": "antoniosanspurs",
    "rebekamasarova": "masarovarebeka",
    "rasingklubmontevideo": "clubmontevideoracing",
    "racingclubmontevideo": "clubmontevideoracing",
}

# Игроки: canonical key → EN display (не сборные)
PERSON_CATALOG: tuple[CatalogEntry, ...] = (
    _e("arnaldimatteo", "Matteo Arnaldi", "Matteo Arnaldi", "Арнальди М.", "Arnaldi M."),
    _e("cobolliflavio", "Flavio Cobolli", "Flavio Cobolli", "Флавио Коболли", "Kobolli F."),
    _e("mensikjakub", "Jakub Mensik", "Jakub Mensik", "Якуб Меншик", "Mensik J."),
    _e("zverevalexander", "Alexander Zverev", "Alexander Zverev", "Александр Зверев", "Zverev A."),
    _e("shnaiderdiana", "Diana Shnaider", "Diana Shnaider", "Шнайдер Д."),
    _e("chwalinskamaja", "Maja Chwalinska", "Maja Chwalinska", "Хвалинска М.", "Chwalinska M."),
    _e("kostyukmarta", "Marta Kostyuk", "Kostyuk M."),
    _e("andreevamirra", "Mirra Andreeva", "Andreeva M."),
    _e("masarovarebeka", "Rebeka Masarova", "Rebeka Masarova", "Ребека Масарова"),
)

ALL_CATALOG: tuple[CatalogEntry, ...] = COUNTRY_CATALOG + PERSON_CATALOG
