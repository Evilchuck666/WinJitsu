.PHONY: help build install install-dev uninstall \
        clean clean-pkgs aur arch

help:
	@echo "Available targets:"
	@echo "  aur          Build and install the AUR package from AUR/"
	@echo "  build        Build the WinJitsu wheel into PKGs/"
	@echo "  clean        Remove build artifacts"
	@echo "  clean-pkgs   Remove all generated wheel files from PKGs/"
	@echo "  install      Build and install the WinJitsu wheel"
	@echo "  uninstall    Uninstall the WinJitsu package"

aur:
	cd AUR && makepkg -si
	rm -rf AUR/src AUR/pkg AUR/*.pkg.tar.zst AUR/WinJitsu

build:
	python -m build --wheel
	mkdir -p PKGs
	mv dist/*.whl PKGs/
	$(MAKE) clean

clean:
	rm -rf dist/ build/ src/WinJitsu.egg-info/

clean-pkgs:
	rm -rf PKGs/

install:
	$(MAKE) build
	pip install --break-system-packages PKGs/winjitsu-*.whl

uninstall:
	pip uninstall -y WinJitsu --break-system-packages
