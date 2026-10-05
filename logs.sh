#!/bin/bash
echo "Streaming logs for AlgoLab... (Press Ctrl+C to stop)"
sudo journalctl -u algolab -f -n 100 -o cat
