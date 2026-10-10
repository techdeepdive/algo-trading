#!/bin/bash
cd /home/project/algo-trading
git pull
pip3 install -r requirements.txt --break-system-packages
cd frontend
npm install
npm run build
cd ..
sudo systemctl restart algoscan
echo "Update complete and server restarted!"
