Name:           printforge
Version:        1.0.0
Release:        1%{?dist}
Summary:        Modern printing application for Fedora Linux

License:        GPL-3.0-or-later
URL:            https://github.com/peteriishak/PrintForge
Source0:        %{url}/archive/v%{version}/%{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools
BuildRequires:  python3-wheel
BuildRequires:  desktop-file-utils
BuildRequires:  libappstream-glib

Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita >= 1.7
Requires:       python3-cups
Requires:       python3-pillow
Requires:       python3-cairo
Requires:       poppler-glib
Requires:       librsvg2
Requires:       hicolor-icon-theme
Recommends:     cups

# Optional formats: syntax highlighting, PostScript/EPS, office documents
Recommends:     python3-pygments
Recommends:     ghostscript
Suggests:       libreoffice-core

%description
PrintForge is a native, modern printing application for Fedora Linux built with
GTK4 and Libadwaita. It makes printing files and images simple while offering
complete control over print settings, live interactive preview, printer
maintenance tools and CUPS integration.

%prep
%autosetup -n PrintForge-%{version}

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files printforge

# Install desktop file
install -D -m 0644 data/io.github.peteriishak.PrintForge.desktop %{buildroot}%{_datadir}/applications/io.github.peteriishak.PrintForge.desktop

# Install AppStream metainfo
install -D -m 0644 data/io.github.peteriishak.PrintForge.metainfo.xml %{buildroot}%{_metainfodir}/io.github.peteriishak.PrintForge.metainfo.xml

# Install icons
install -D -m 0644 data/icons/hicolor/scalable/apps/io.github.peteriishak.PrintForge.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.peteriishak.PrintForge.svg
install -D -m 0644 data/icons/hicolor/symbolic/apps/io.github.peteriishak.PrintForge-symbolic.svg %{buildroot}%{_datadir}/icons/hicolor/symbolic/apps/io.github.peteriishak.PrintForge-symbolic.svg

for size in 48 64 128; do
    install -D -m 0644 data/icons/hicolor/${size}x${size}/apps/io.github.peteriishak.PrintForge.png \
        %{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps/io.github.peteriishak.PrintForge.png
done

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.peteriishak.PrintForge.desktop
appstream-util validate-relax --nonet %{buildroot}%{_metainfodir}/io.github.peteriishak.PrintForge.metainfo.xml

%files -f %{pyproject_files}
%license LICENSE
%doc README.md
%{_bindir}/printforge
%{_datadir}/applications/io.github.peteriishak.PrintForge.desktop
%{_metainfodir}/io.github.peteriishak.PrintForge.metainfo.xml
%{_datadir}/icons/hicolor/*/apps/io.github.peteriishak.PrintForge*

%changelog
* Fri Nov 27 2026 Peter Habib <343233346+peteriishak@users.noreply.github.com> - 1.0.0-1
- Initial public release
