@echo off
title Llama-Server (gemma-4-26B-A4B-it-qat-UD-Q4_K_XL)
echo Launching gemma-4-26B-A4B-it-qat-UD-Q4_K_XL on port 8081...
"C:\Program Files\Android\Android Studio\plugins\gemini\resources\llamacpp\llama-server.exe" -m "S:/LLM/gemma-4 QAT/26B-A4B/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf" -c 32768 -ngl 8 --port 8081 --host 127.0.0.1 -np 1 --no-warmup -sm none -fa on --cache-type-k q8_0 --cache-type-v q5_1
pause
