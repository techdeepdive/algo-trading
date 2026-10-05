#!/bin/bash
echo "Streaming logs for AlgoScan... (Press Ctrl+C to stop)"
sudo journalctl -u algoscan -f -n 100 -o cat
