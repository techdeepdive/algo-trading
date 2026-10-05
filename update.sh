#!/bin/bash
cd /home/project/algo-trading
git pull
cd frontend
npm install
npm run build
cd ..
sudo systemctl restart algolab
echo "Update complete and server restarted!"
