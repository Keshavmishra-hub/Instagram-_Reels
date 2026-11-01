"""Source credibility: tier by domain, registrable domain for independence checks."""

from __future__ import annotations

import re
from urllib.parse import urlparse

MULTI_PART_SUFFIXES = {
    "co.uk", "ac.uk", "gov.uk", "org.uk", "nhs.uk", "gov.in", "nic.in", "ac.in", "co.in", "org.in", "res.in", "edu.in",
    "com.au", "gov.au", "edu.au", "org.au", "co.nz", "govt.nz", "ac.nz", "gc.ca", "co.jp", "go.jp", "ac.jp",
    "com.br", "gov.br", "gob.mx", "gob.es", "gouv.fr", "co.za", "gov.za", "ac.za", "com.cn", "gov.cn", "edu.cn",
    "com.sg", "gov.sg", "edu.sg", "com.pk", "gov.pk", "gov.bd", "gov.lk", "go.kr", "ac.kr", "gov.ng", "go.ke",
}

GOV_PATTERNS = [
    r"\.gov$", r"\.gov\.[a-z]{2}$", r"\.nic\.in$", r"\.gov\.in$", r"\.gouv\.fr$", r"\.gc\.ca$", r"\.go\.jp$", r"\.gob\.[a-z]{2}$",
    r"\.mil$", r"\.bund\.de$", r"\.admin\.ch$", r"\.govt\.nz$", r"(^|\.)regjeringen\.no$", r"(^|\.)government\.[a-z]{2,3}$",
    r"(^|\.)rbi\.org\.in$", r"(^|\.)sebi\.gov\.in$", r"(^|\.)nasa\.gov$", r"(^|\.)isro\.gov\.in$", r"(^|\.)ssb\.no$",
    r"(^|\.)parliament\.uk$", r"(^|\.)sansad\.in$", r"(^|\.)europarl\.europa\.eu$", r"(^|\.)ons\.gov\.uk$", r"(^|\.)icar\.org\.in$",
    r"(^|\.)nddb\.coop$", r"(^|\.)federalreserve\.gov$", r"(^|\.)ecb\.europa\.eu$", r"(^|\.)bankofengland\.co\.uk$",
]
INTERGOV = {
    "un.org", "fao.org", "who.int", "worldbank.org", "imf.org", "oecd.org", "wto.org", "unesco.org", "unicef.org", "undp.org",
    "wfp.org", "iaea.org", "wmo.int", "itu.int", "ilo.org", "unep.org", "ipcc.ch", "cgiar.org", "icrisat.org", "icarda.org",
    "irri.org", "cimmyt.org", "croptrust.org", "nordgen.org", "europa.eu", "iea.org", "irena.org", "unhcr.org", "ifad.org",
    "adb.org", "afdb.org", "wipo.int", "unfccc.int", "cbd.int", "iucn.org", "gavi.org", "bis.org", "nato.int", "iom.int",
}
ACADEMIC = {
    "nature.com", "science.org", "sciencedirect.com", "springer.com", "link.springer.com", "wiley.com", "tandfonline.com",
    "pnas.org", "thelancet.com", "nejm.org", "bmj.com", "plos.org", "arxiv.org", "nih.gov", "jstor.org", "cambridge.org",
    "oup.com", "frontiersin.org", "mdpi.com", "cell.com", "acs.org", "aps.org", "iop.org", "royalsocietypublishing.org",
    "biorxiv.org", "medrxiv.org", "ssrn.com", "nber.org", "doi.org", "semanticscholar.org", "researchgate.net",
}
NEWS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com", "theguardian.com", "washingtonpost.com", "wsj.com",
    "ft.com", "economist.com", "bloomberg.com", "aljazeera.com", "npr.org", "cnn.com", "thehindu.com", "indianexpress.com",
    "hindustantimes.com", "livemint.com", "business-standard.com", "indiatimes.com", "ndtv.com", "scroll.in", "theprint.in",
    "downtoearth.org.in", "thehindubusinessline.com", "nationalgeographic.com", "smithsonianmag.com", "scientificamerican.com",
    "newscientist.com", "dw.com", "france24.com", "abc.net.au", "cbc.ca", "lemonde.fr", "spiegel.de", "scmp.com",
    "japantimes.co.jp", "theatlantic.com", "time.com", "nbcnews.com", "cbsnews.com", "pbs.org", "axios.com", "politico.com",
    "forbes.com", "fortune.com", "cnbc.com", "moneycontrol.com", "deccanherald.com", "tribuneindia.com", "telegraphindia.com",
    "news18.com", "firstpost.com", "thewire.in", "frontline.thehindu.com", "nrk.no", "yle.fi", "svt.se",
}
REFERENCE = {"britannica.com", "wikipedia.org", "wikimedia.org", "si.edu", "loc.gov", "archives.gov", "metmuseum.org", "worldhistory.org", "ourworldindata.org"}
INDUSTRY = {"statista.com", "mckinsey.com", "pwc.com", "deloitte.com", "ey.com", "kpmg.com", "bcg.com", "ibef.org", "nasscom.in", "gartner.com", "iea.org"}
NGO = {"wwf.org", "worldwildlife.org", "greenpeace.org", "oxfam.org", "gatesfoundation.org", "msf.org", "icrc.org", "amnesty.org", "hrw.org"}
TERTIARY = {"wikipedia.org", "wikimedia.org"}


def hostname(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def registrable_domain(url_or_host: str) -> str:
    host = hostname(url_or_host) if "/" in url_or_host or ":" in url_or_host else url_or_host.lower()
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in MULTI_PART_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _in(host: str, domains: set[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def classify(url: str) -> str:
    host = hostname(url)
    if any(re.search(p, host) for p in GOV_PATTERNS):
        return "government"
    if _in(host, INTERGOV) or host.endswith(".int"):
        return "intergovernmental"
    if _in(host, ACADEMIC) or re.search(r"\.(edu|ac\.[a-z]{2}|edu\.[a-z]{2})$", host):
        return "academic"
    if _in(host, NEWS):
        return "news"
    if _in(host, REFERENCE):
        return "reference"
    if _in(host, INDUSTRY):
        return "industry"
    if _in(host, NGO):
        return "ngo"
    return "other"


def is_tertiary(url: str) -> bool:
    return _in(hostname(url), TERTIARY)


TIER_WEIGHT = {
    "government": 1.0, "intergovernmental": 1.0, "academic": 0.95, "company_official": 0.85, "news": 0.75,
    "reference": 0.6, "industry": 0.6, "ngo": 0.6, "other": 0.35,
}
STRONG_TIERS = {"government", "intergovernmental", "academic", "company_official"}
