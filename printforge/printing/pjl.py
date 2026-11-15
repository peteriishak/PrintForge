"""Job identification — puts the User ID on the printer's panel and job log.

Office printers (Ricoh, HP, Kyocera, …) read the user and job name from PJL
commands sent ahead of the page data. A generic PostScript driver sends none,
so the printer shows a blank User ID. For those queues PrintForge runs the
queue's own CUPS filters, adds the PJL commands, and submits the result as
printer-ready data.
"""

from __future__ import annotations

import glob
import logging
import os
import re
import shutil
import socket
import subprocess
import time
from typing import Optional
from urllib.parse import unquote, urlparse

log = logging.getLogger(__name__)

UEL = b"\x1b%-12345X"  # Universal Exit Language: switches the printer into PJL
PRINTER_READY_FORMAT = "application/vnd.cups-postscript"

# Ricoh and the brands it sells the same machines under
_RICOH_FAMILY = ("ricoh", "savin", "lanier", "gestetner", "nrg", "nashuatec", "rex-rotary", "infotec")
_RICOH_USER_ID_LENGTH = 8
_FILTER_TIMEOUT_SECONDS = 600


def get_device_name() -> str:
    """Return this computer's device name, as shown in GNOME Settings → About.

    Uses the pretty hostname from /etc/machine-info, falling back to the
    static hostname.
    """
    try:
        with open("/etc/machine-info", encoding="utf-8") as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key == "PRETTY_HOSTNAME":
                    value = value.strip().strip('"').strip("'")
                    if value:
                        return value
    except OSError:
        pass
    return socket.gethostname() or "PrintForge"


def resolve_user_id(configured: str = "") -> str:
    """The User ID jobs are sent under: the configured one, or the device name."""
    return configured.strip() or get_device_name()


def panel_user_id(user_id: str) -> str:
    """`user_id` as a printer panel can show it: up to 8 letters and digits."""
    cleaned = re.sub(r"[^A-Za-z0-9]", "", user_id)[:_RICOH_USER_ID_LENGTH]
    return cleaned or "user"


def _pjl_string(text: str, limit: int = 80) -> str:
    """Make `text` safe inside a quoted PJL value."""
    text = text.replace('"', "'")
    text = "".join(ch if " " <= ch <= "~" else "?" for ch in text)
    return text[:limit]


def build_pjl_header(user_id: str, title: str, host: str = "", when: Optional[float] = None) -> bytes:
    """PJL commands that identify the job, ending with the switch to PostScript."""
    stamp = time.localtime(when)
    name = _pjl_string(os.path.basename(title) or "PrintForge Job")
    user = _pjl_string(user_id, 32)
    lines = [
        f'@PJL JOB NAME="{name}"',
        f'@PJL SET USERID="{panel_user_id(user_id)}"',  # Ricoh family
        f'@PJL SET USERNAME="{user}"',                   # HP and most others
        f'@PJL SET HOSTLOGINNAME="{user}"',
        f'@PJL SET HOSTNAME="{_pjl_string(host or socket.gethostname(), 32)}"',
        f'@PJL SET JOBNAME="{name}"',
        f'@PJL SET DATE="{time.strftime("%Y/%m/%d", stamp)}"',
        f'@PJL SET TIME="{time.strftime("%H:%M:%S", stamp)}"',
        "@PJL ENTER LANGUAGE=POSTSCRIPT",
    ]
    return UEL + "".join(line + "\n" for line in lines).encode("ascii")


def build_pjl_footer(title: str) -> bytes:
    name = _pjl_string(os.path.basename(title) or "PrintForge Job")
    return UEL + f'@PJL EOJ NAME="{name}"\n'.encode("ascii") + UEL


def _device_id_fields(device_id: str) -> dict[str, str]:
    """Parse an IEEE 1284 device ID ('MFG:RICOH;CMD:PJL,PCL;…') into a dict."""
    fields = {}
    for part in device_id.split(";"):
        key, sep, value = part.partition(":")
        if sep:
            fields[key.strip().upper()] = value.strip()
    return fields


def _commands(device_id: str) -> list[str]:
    fields = _device_id_fields(device_id)
    raw = fields.get("CMD") or fields.get("COMMAND SET") or ""
    return [command.strip().upper() for command in raw.split(",") if command.strip()]


def _usb_device_id(device_uri: str) -> str:
    """IEEE 1284 ID the printer behind a usb:// URI reports about itself."""
    parsed = urlparse(device_uri)
    maker = unquote(parsed.netloc).lower()
    model = unquote(parsed.path.lstrip("/")).lower()
    for path in glob.glob("/sys/class/usbmisc/lp*/device/ieee1284_id"):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                device_id = f.read().strip()
        except OSError:
            continue
        fields = _device_id_fields(device_id)
        found_maker = (fields.get("MFG") or fields.get("MANUFACTURER") or "").lower()
        found_model = (fields.get("MDL") or fields.get("MODEL") or "").lower()
        if found_maker == maker and found_model in (model, f"{maker} {model}"):
            return device_id
    return ""


def device_speaks_pjl(device_uri: str, device_id: str = "", make_model: str = "") -> bool:
    """Whether the printer understands PJL job commands.

    Trusts what the device reports about itself; a generic driver's own
    device ID only describes the driver.
    """
    if "PJL" in _commands(device_id):
        return True
    if device_uri.lower().startswith("usb://"):
        usb_id = _usb_device_id(device_uri)
        if usb_id:
            return "PJL" in _commands(usb_id)
    # Can't ask the device: every PostScript printer of the Ricoh family speaks PJL
    described = f"{unquote(device_uri)} {make_model}".lower()
    return any(brand in described for brand in _RICOH_FAMILY)


def _filter_option(name: str, value: str) -> str:
    if re.search(r'[\s"\'\\]', value):
        value = '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f"{name}={value}"


def render_printer_ready(
    ppd_path: str,
    pdf_path: str,
    output_path: str,
    user: str,
    title: str,
    options: dict[str, str],
) -> bool:
    """Run the queue's CUPS filters over `pdf_path`, writing printer-ready PostScript.

    This is the conversion the CUPS scheduler would do itself, with the same
    driver and job options, so the pages come out identical.
    """
    cupsfilter = shutil.which("cupsfilter") or shutil.which("cupsfilter", path="/usr/sbin:/usr/lib/cups/daemon")
    if not cupsfilter:
        log.info("cupsfilter not found")
        return False

    command = [
        cupsfilter, "-p", ppd_path,
        "-i", "application/pdf", "-m", PRINTER_READY_FORMAT,
        "-U", user, "-t", title,
        "-n", str(options.get("copies", "1")),
    ]
    for name, value in options.items():
        if name != "copies":  # passed with -n, as the scheduler does
            command += ["-o", _filter_option(name, str(value))]
    command.append(pdf_path)

    try:
        with open(output_path, "wb") as out:
            result = subprocess.run(
                command, stdout=out, stderr=subprocess.PIPE, timeout=_FILTER_TIMEOUT_SECONDS,
            )
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("cupsfilter failed: %s", e)
        return False

    if result.returncode != 0:
        log.warning("cupsfilter exited with %d: %s", result.returncode,
                    result.stderr.decode("utf-8", "replace")[-500:])
        return False
    try:
        with open(output_path, "rb") as f:
            return f.read(2) == b"%!"
    except OSError:
        return False


def tag_job(ps_path: str, output_path: str, user_id: str, title: str) -> None:
    """Wrap printer-ready PostScript in the PJL commands that identify the job."""
    with open(output_path, "wb") as out:
        out.write(build_pjl_header(user_id, title))
        with open(ps_path, "rb") as ps:
            shutil.copyfileobj(ps, out)
        out.write(build_pjl_footer(title))
