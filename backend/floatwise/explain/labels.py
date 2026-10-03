"""Bangla / English strings and number formatting for explanations (R-CODE-6, R-CODE-7)."""

from __future__ import annotations

import datetime as dt

BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
ASCII_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

BN_MONTHS = ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর",
             "অক্টোবর", "নভেম্বর", "ডিসেম্বর"]  # fmt: skip


def lakh(n: float) -> str:
    """Bangladeshi digit grouping: 1234567 -> '12,34,567'."""
    neg = n < 0
    s = str(abs(int(round(n))))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return ("-" if neg else "") + s


def taka(n: float, lang: str = "en") -> str:
    s = "৳" + lakh(n)
    return s.translate(BN_DIGITS) if lang == "bn" else s


def num(n: float | int | str, lang: str = "en") -> str:
    s = str(n)
    return s.translate(BN_DIGITS) if lang == "bn" else s


def pct(p: float, lang: str = "en") -> str:
    return num(f"{int(round(100 * p))}%", lang)


def date_str(d: dt.date, lang: str = "en") -> str:
    if lang == "bn":
        return f"{num(d.day, 'bn')} {BN_MONTHS[d.month - 1]}"
    return d.strftime("%-d %B")


ARCHETYPES = {
    "urban_residential": {"en": "urban residential area", "bn": "শহুরে আবাসিক এলাকা"},
    "garment_belt": {"en": "garment-factory area", "bn": "গার্মেন্টস এলাকা"},
    "rural_remittance": {"en": "rural remittance area", "bn": "গ্রামীণ রেমিট্যান্স এলাকা"},
    "market_hub": {"en": "market hub", "bn": "বাজার এলাকা"},
    "university_area": {"en": "university area", "bn": "বিশ্ববিদ্যালয় এলাকা"},
}

ACTIONS = {
    "TOP_UP_CASH": {"en": "Top up cash", "bn": "নগদ টাকা বাড়ান"},
    "TOP_UP_EFLOAT": {"en": "Top up e-float", "bn": "ই-ফ্লোট বাড়ান"},
    "NO_ACTION": {"en": "No action needed", "bn": "কোনো পদক্ষেপ লাগবে না"},
    "NEEDS_EXTRA_FLOAT": {"en": "Needs extra float — escalate", "bn": "অতিরিক্ত ফ্লোট দরকার — ঊর্ধ্বতনকে জানান"},
}

EVENTS = {
    "Eid-ul-Fitr": {"en": "Eid-ul-Fitr", "bn": "ঈদুল ফিতর"},
    "Eid-ul-Adha": {"en": "Eid-ul-Adha", "bn": "ঈদুল আযহা"},
    "Pohela Boishakh": {"en": "Pohela Boishakh", "bn": "পহেলা বৈশাখ"},
    "Salary window": {"en": "salary days", "bn": "বেতনের দিন"},
    "Allowance disbursement": {"en": "allowance disbursement", "bn": "ভাতা বিতরণ"},
}

# feature -> (en, bn) label used for SHAP drivers
FEATURES = {
    "h": ("Forecast horizon", "পূর্বাভাসের দিন"),
    "dow": ("Day of week", "সপ্তাহের দিন"),
    "is_weekend": ("Weekend", "সাপ্তাহিক ছুটি"),
    "day_of_month": ("Day of month (salary cycle)", "মাসের তারিখ (বেতন চক্র)"),
    "is_salary_window": ("Salary days", "বেতনের দিন"),
    "g2p_day_index": ("Allowance disbursement (G2P) day", "ভাতা বিতরণের দিন"),
    "days_to_eid_fitr": ("Days to Eid-ul-Fitr", "ঈদুল ফিতর পর্যন্ত দিন"),
    "days_to_eid_adha": ("Days to Eid-ul-Adha", "ঈদুল আযহা পর্যন্ত দিন"),
    "days_after_eid": ("Days since Eid", "ঈদের পর দিন"),
    "is_ramadan": ("Ramadan", "রমজান"),
    "is_boishakh": ("Pohela Boishakh", "পহেলা বৈশাখ"),
    "is_public_holiday": ("Public holiday", "সরকারি ছুটি"),
    "archetype_code": ("Area type", "এলাকার ধরন"),
    "district_code": ("District", "জেলা"),
    "capacity_ratio": ("Float size vs volume", "লেনদেনের তুলনায় ফ্লোট"),
    "ci_co_ratio": ("Cash-in vs cash-out mix", "ক্যাশ ইন বনাম ক্যাশ আউট"),
}
_SIDE = {"co": ("cash-out", "ক্যাশ আউট"), "ci": ("cash-in", "ক্যাশ ইন")}
_SIDE_FEATURES = {
    "log_scale": ("Typical daily {s}", "সাধারণ দৈনিক {s}"),
    "lag0": ("Today's {s}", "আজকের {s}"),
    "lag1": ("Yesterday's {s}", "গতকালের {s}"),
    "same_dow_7": ("{s} same day last week", "গত সপ্তাহের একই দিনের {s}"),
    "same_dow_14": ("{s} same day 2 weeks ago", "দুই সপ্তাহ আগের একই দিনের {s}"),
    "mean7": ("Last 7 days' {s}", "গত ৭ দিনের {s}"),
    "mean7_prev": ("{s} the week before", "আগের সপ্তাহের {s}"),
    "std7": ("Recent {s} volatility", "সাম্প্রতিক {s} ওঠানামা"),
    "max28": ("Peak {s} in 4 weeks", "৪ সপ্তাহের সর্বোচ্চ {s}"),
    "prev_fitr_mult": ("{s} jump at last Eid-ul-Fitr", "গত ঈদুল ফিতরে {s} বৃদ্ধি"),
    "prev_adha_mult": ("{s} jump at last Eid-ul-Adha", "গত ঈদুল আযহায় {s} বৃদ্ধি"),
    "stockouts_7d": ("Recent {s} stockouts", "সাম্প্রতিক {s} ঘাটতি"),
}
for _p, (_en, _bn) in _SIDE.items():
    for _k, (_fe, _fb) in _SIDE_FEATURES.items():
        FEATURES[f"{_p}_{_k}"] = (_fe.format(s=_en).capitalize(), _fb.format(s=_bn))


def feature_label(feature: str, lang: str) -> str:
    en, bn = FEATURES.get(feature, (feature, feature))
    return bn if lang == "bn" else en


DOW = {"en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
       "bn": ["সোম", "মঙ্গল", "বুধ", "বৃহস্পতি", "শুক্র", "শনি", "রবি"]}  # fmt: skip
