# Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Kerakli dasturlarni o'rnatish
RUN apt-get update && apt-get install -y git wget && rm -rf /var/lib/apt/lists/*

# Real-ESRGAN yuklab olish
RUN git clone https://github.com/xinntao/Real-ESRGAN.git
WORKDIR /app/Real-ESRGAN

# CPU uchun PyTorch
RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN pip install -r requirements.txt
RUN python setup.py develop

# Modelni yuklab olish
RUN mkdir -p weights
RUN wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth -O weights/RealESRGAN_x4plus.pth

# Asosiy bot kodingizni nusxalash
WORKDIR /app
COPY . .

# Botni ishga tushirish
CMD ["python3", "main.py"]
