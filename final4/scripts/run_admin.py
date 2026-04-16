#!/usr/bin/env python3
"""Запуск админ-панели Final 4"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.admin.app import create_app

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('ADMIN_PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
