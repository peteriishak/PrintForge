"""PPD inspection — the options a printer's driver really accepts.

IPP attributes describe a queue in generic keywords ('top', 'manual'), but a
job only changes the tray when it names the driver's own choice ('Upper',
'Manual'). This module reads those choices from the queue's PPD.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# PPD options that duplicate another option or aren't user choices
_HIDDEN_OPTIONS = {"PageRegion"}

# InputSlot choice → IPP media-source keyword, as CUPS maps them
_SOURCE_KEYWORDS = {
    "default": "auto",
    "cassette": "main",
    "phototray": "photo",
    "cdtray": "disc",
    "mp": "by-pass-tray",
    "mptray": "by-pass-tray",
    "largecapacity": "large-capacity",
    "middle": "middle",
    "upper": "top",
    "side": "side",
    "roll": "main-roll",
}
_SOURCE_PREFIXES = (("auto", "auto"), ("multipurpose", "by-pass-tray"), ("lower", "bottom"))


def pwg_source_keyword(choice: str) -> str:
    """IPP media-source keyword CUPS reports for an InputSlot choice ('Upper' → 'top')."""
    lowered = choice.lower()
    if lowered in _SOURCE_KEYWORDS:
        return _SOURCE_KEYWORDS[lowered]
    for prefix, keyword in _SOURCE_PREFIXES:
        if lowered.startswith(prefix):
            return keyword
    # 'Tray1' → 'tray-1', 'ManualFeed' → 'manual-feed'
    hyphenated = re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Za-z])", "-", choice)
    return re.sub(r"[^a-z0-9]+", "-", hyphenated.lower()).strip("-")


@dataclass(frozen=True)
class PpdChoice:
    value: str
    label: str


@dataclass
class PpdOption:
    keyword: str
    label: str
    default: str = ""
    choices: list[PpdChoice] = field(default_factory=list)
    group: str = ""
    is_installable: bool = False

    def has_choice(self, value: str) -> bool:
        return any(choice.value == value for choice in self.choices)


@dataclass
class PpdInfo:
    """The parts of a PPD that PrintForge acts on."""

    nickname: str = ""
    options: list[PpdOption] = field(default_factory=list)
    # No cupsFilter line: job data reaches the printer as PostScript
    is_postscript: bool = False
    # The driver already wraps jobs in its own job-control (PJL) commands
    has_jcl: bool = False

    def option(self, keyword: str) -> Optional[PpdOption]:
        return next((opt for opt in self.options if opt.keyword == keyword), None)

    @property
    def trays(self) -> list[PpdChoice]:
        slot = self.option("InputSlot")
        return list(slot.choices) if slot else []

    @property
    def auto_tray(self) -> str:
        """The InputSlot choice that lets the printer pick the tray, or ''."""
        return next((c.value for c in self.trays if pwg_source_keyword(c.value) == "auto"), "")

    @property
    def is_generic(self) -> bool:
        """A stand-in driver that doesn't know this printer's own features."""
        return self.nickname.lower().startswith("generic")


def read_ppd(path: str) -> Optional[PpdInfo]:
    """Parse the PPD at `path`. Returns None if it can't be read."""
    try:
        import cups
        ppd = cups.PPD(path)
    except Exception as e:
        log.warning("Cannot read PPD %s: %s", path, e)
        return None

    try:
        ppd.localize()
    except Exception:
        pass  # Untranslated labels are fine

    def attr(name: str) -> str:
        found = ppd.findAttr(name)
        return found.value if found and found.value else ""

    info = PpdInfo(
        nickname=attr("NickName"),
        is_postscript=not (ppd.findAttr("cupsFilter") or ppd.findAttr("cupsFilter2")),
        has_jcl=bool(attr("JCLBegin")),
    )
    for group in ppd.optionGroups:
        for opt in group.options:
            if opt.keyword in _HIDDEN_OPTIONS or opt.ui == cups.PPD_UI_PICKMANY:
                continue
            info.options.append(PpdOption(
                keyword=opt.keyword,
                label=opt.text or opt.keyword,
                default=opt.defchoice or "",
                choices=[PpdChoice(c["choice"], c["text"] or c["choice"]) for c in opt.choices],
                group=group.text or group.name,
                is_installable=group.name == "InstallableOptions",
            ))
    return info
