Name:           printforge
Version:        1.0.0
Release:        1%{?dist}
Summary:        Modern printing application for Fedora Linux

License:        GPL-3.0-or-later
URL:            https://github.com/printforge/printforge
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools
BuildRequires:  desktop-file-utils
BuildRequires:  libappstream-glib

Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       python3-cups
Requires:       python3-pillow
Requires:       python3-cairo
Requires:       poppler-glib
Requires:       librsvg2
Requires:       hicolor-icon-theme

%description
PrintForge is a native, modern printing application for Fedora Linux built with
GTK4 and Libadwaita. It makes printing files and images simple while offering
complete control over print settings, live interactive preview, and CUPS
integration.

%prep
%autosetup -n %{name}-%{version}

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files printforge

# Install desktop file
install -D -m 0644 data/io.github.printforge.desktop %{buildroot}%{_datadir}/applications/io.github.printforge.desktop

# Install AppStream metainfo
install -D -m 0644 data/io.github.printforge.metainfo.xml %{buildroot}%{_metainfodir}/io.github.printforge.metainfo.xml

# Install icons
install -D -m 0644 data/icons/hicolor/scalable/apps/io.github.printforge.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.printforge.svg
install -D -m 0644 data/icons/hicolor/symbolic/apps/io.github.printforge-symbolic.svg %{buildroot}%{_datadir}/icons/hicolor/symbolic/apps/io.github.printforge-symbolic.svg

for size in 48 64 128; do
    install -D -m 0644 data/icons/hicolor/${size}x${size}/apps/io.github.printforge.png \
        %{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps/io.github.printforge.png
done

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.printforge.desktop
appstream-util validate-relax --nonet %{buildroot}%{_metainfodir}/io.github.printforge.metainfo.xml

%files -f %{pyproject_files}
%license LICENSE
%doc README.md
%{_bindir}/printforge
%{_datadir}/applications/io.github.printforge.desktop
%{_metainfodir}/io.github.printforge.metainfo.xml
%{_datadir}/icons/hicolor/*/apps/io.github.printforge*

%changelog
* Sun Jan 01 2025 PrintForge Contributors <contributors@printforge.org> - 1.0.0-1
- Initial release for Fedora Linux
