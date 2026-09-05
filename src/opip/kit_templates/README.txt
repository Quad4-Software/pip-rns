Airgap kit (opip)

AppImage-style (if this kit was built with --as-app):
  ./NomadNet
  ./Run

Classic install into a venv:
  ./install.sh

1. If runtime/ exists, Python is bundled. Otherwise you need python3.
2. Verify: python3 opip.pyz verify packages/*.opip
3. Bootstrap another machine with no pip:
   python3 get-opip.py --from-dir . -o ~/tools

Tools on this stick:
  opip.pyz / pip-rns.pyz / get-opip.py
