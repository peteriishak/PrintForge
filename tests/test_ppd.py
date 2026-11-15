"""Tests for driver (PPD) inspection and paper tray selection."""

import os

import pytest

from printforge.config.print_settings import PrintSettings
from printforge.printing.capabilities import PrinterCapabilities
from printforge.printing.ppd import PpdChoice, PpdInfo, PpdOption, pwg_source_keyword, read_ppd

MINIMAL_PPD = """*PPD-Adobe: "4.3"
*FormatVersion: "4.3"
*FileVersion: "1.0"
*LanguageVersion: English
*LanguageEncoding: ISOLatin1
*PCFileName: "TEST.PPD"
*Manufacturer: "Generic"
*Product: "(Test)"
*ModelName: "Generic Test Printer"
*ShortNickName: "Generic Test Printer"
*NickName: "Generic Test Printer"
*PSVersion: "(3010.000) 0"
*LanguageLevel: "3"
*ColorDevice: True
*DefaultColorSpace: RGB
*FileSystem: False
*Throughput: "1"
*LandscapeOrientation: Plus90
*TTRasterizer: Type42
*OpenUI *PageSize/Media Size: PickOne
*OrderDependency: 10 AnySetup *PageSize
*DefaultPageSize: Letter
*PageSize Letter/US Letter: "<</PageSize[612 792]>>setpagedevice"
*PageSize A4/A4: "<</PageSize[595 842]>>setpagedevice"
*CloseUI: *PageSize
*OpenUI *PageRegion/Media Size: PickOne
*OrderDependency: 10 AnySetup *PageRegion
*DefaultPageRegion: Letter
*PageRegion Letter/US Letter: "<</PageSize[612 792]>>setpagedevice"
*PageRegion A4/A4: "<</PageSize[595 842]>>setpagedevice"
*CloseUI: *PageRegion
*DefaultImageableArea: Letter
*ImageableArea Letter/US Letter: "18 36 594 756"
*ImageableArea A4/A4: "18 36 577 806"
*DefaultPaperDimension: Letter
*PaperDimension Letter/US Letter: "612 792"
*PaperDimension A4/A4: "595 842"
*OpenUI *InputSlot/Media Source: PickOne
*OrderDependency: 10 AnySetup *InputSlot
*DefaultInputSlot: Default
*InputSlot Default/Printer Default: ""
*InputSlot Upper/Cassette: "<</ManualFeed false>>setpagedevice"
*InputSlot Manual/Manual Feed: "<</ManualFeed true>>setpagedevice"
*CloseUI: *InputSlot
*DefaultFont: Courier
*Font Courier: Standard "(1.05)" Standard ROM
"""


def _generic_ppd() -> PpdInfo:
    """The driver of a generic PostScript queue, as CUPS ships it."""
    return PpdInfo(
        nickname="Generic PostScript Printer",
        is_postscript=True,
        options=[
            PpdOption("PageSize", "Media Size", "Letter", [PpdChoice("Letter", "US Letter"), PpdChoice("A4", "A4")]),
            PpdOption("InputSlot", "Media Source", "Default", [
                PpdChoice("Default", "Printer Default"),
                PpdChoice("Upper", "Cassette"),
                PpdChoice("Manual", "Manual Feed"),
            ]),
        ],
    )


class TestSourceKeywords:
    @pytest.mark.parametrize("choice, keyword", [
        ("Default", "auto"),
        ("Auto", "auto"),
        ("AutoSelect", "auto"),
        ("Upper", "top"),
        ("Lower", "bottom"),
        ("Manual", "manual"),
        ("Cassette", "main"),
        ("MultiPurpose", "by-pass-tray"),
        ("Tray1", "tray-1"),
        ("ManualFeed", "manual-feed"),
    ])
    def test_matches_cups_mapping(self, choice, keyword):
        assert pwg_source_keyword(choice) == keyword


class TestPpdInfo:
    def test_trays_and_auto_tray(self):
        ppd = _generic_ppd()
        assert [tray.value for tray in ppd.trays] == ["Default", "Upper", "Manual"]
        assert ppd.auto_tray == "Default"
        assert ppd.is_generic

    def test_no_auto_tray(self):
        ppd = PpdInfo(options=[PpdOption("InputSlot", "Tray", "Tray1", [PpdChoice("Tray1", "Tray 1")])])
        assert ppd.auto_tray == ""

    def test_read_ppd(self, tmp_dir):
        pytest.importorskip("cups")
        path = os.path.join(tmp_dir, "test.ppd")
        with open(path, "w") as f:
            f.write(MINIMAL_PPD)

        ppd = read_ppd(path)
        assert ppd is not None
        assert ppd.is_postscript and not ppd.has_jcl
        assert ppd.option("PageRegion") is None  # duplicates PageSize
        assert ppd.option("PageSize").default == "Letter"
        assert [(c.value, c.label) for c in ppd.trays] == [
            ("Default", "Printer Default"), ("Upper", "Cassette"), ("Manual", "Manual Feed"),
        ]

    def test_read_ppd_missing_file(self, tmp_dir):
        pytest.importorskip("cups")
        assert read_ppd(os.path.join(tmp_dir, "nope.ppd")) is None


class TestTraySelection:
    def test_labels_come_from_the_driver(self):
        caps = PrinterCapabilities(supported_sources=["auto", "top", "manual"], ppd=_generic_ppd())
        assert caps.get_tray_labels() == [("Cassette", "Upper"), ("Manual Feed", "Manual")]

    def test_labels_without_a_driver(self):
        caps = PrinterCapabilities(supported_sources=["auto", "tray-1", "manual"])
        assert caps.get_tray_labels() == [("Tray 1", "tray-1"), ("Manual Feed", "manual")]

    def test_automatic_names_the_drivers_auto_choice(self):
        caps = PrinterCapabilities(ppd=_generic_ppd())
        assert caps.tray_job_options("") == {"InputSlot": "Default"}

    def test_picked_tray(self):
        caps = PrinterCapabilities(ppd=_generic_ppd())
        assert caps.tray_job_options("Upper") == {"InputSlot": "Upper"}

    def test_ipp_keyword_is_translated(self):
        """'top' is what older settings saved; the driver only knows 'Upper'."""
        caps = PrinterCapabilities(ppd=_generic_ppd())
        assert caps.tray_job_options("top") == {"InputSlot": "Upper"}

    def test_unknown_tray_falls_back_to_automatic(self):
        caps = PrinterCapabilities(ppd=_generic_ppd())
        assert caps.tray_job_options("tray-9") == {"InputSlot": "Default"}

    def test_without_a_driver(self):
        caps = PrinterCapabilities(supported_sources=["auto", "tray-1"])
        assert caps.tray_job_options("") == {}
        assert caps.tray_job_options("tray-1") == {"media-source": "tray-1"}


class TestTrayInCupsOptions:
    def test_driver_tray(self):
        caps = PrinterCapabilities(ppd=_generic_ppd())
        opts = PrintSettings(tray="Upper").to_cups_options(caps)
        assert opts["InputSlot"] == "Upper"
        assert opts["media"] == "iso_a4_210x297mm"

    def test_automatic_tray(self):
        caps = PrinterCapabilities(ppd=_generic_ppd())
        assert PrintSettings().to_cups_options(caps)["InputSlot"] == "Default"

    def test_tray_without_a_driver_rides_on_media(self):
        caps = PrinterCapabilities(supported_sources=["tray-1"])
        opts = PrintSettings(tray="tray-1").to_cups_options(caps)
        assert opts["media"] == "iso_a4_210x297mm,tray-1"
        assert "InputSlot" not in opts

    def test_without_capabilities(self):
        assert PrintSettings(tray="Upper").to_cups_options()["InputSlot"] == "Upper"
        assert "InputSlot" not in PrintSettings().to_cups_options()

    def test_custom_paper_is_sent(self):
        settings = PrintSettings(paper_size_name="Custom", custom_paper_width_mm=100, custom_paper_height_mm=150.5)
        assert settings.to_cups_options()["media"] == "Custom.100x150.5mm"
