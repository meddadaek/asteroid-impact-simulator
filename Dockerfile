# Orbital Sentinel -- container image for Hugging Face Spaces (or any host).
#
# Only runtime artefacts are copied in. The raw JPL and GeoNames dumps are
# build-time inputs: everything the running app needs has already been reduced
# to backend/data/{land_mask.npy, cities.npz, neo_index.json}, which together
# come to under 2 MB instead of 19.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Pillow is deliberately absent: it is only used to rasterise the land mask at
# asset-build time, and the resulting .npy is copied in below already made.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/app        backend/app
COPY backend/models     backend/models
COPY backend/data       backend/data
COPY frontend           frontend

# Hugging Face Spaces routes to 7860 by default.
ENV PORT=7860
EXPOSE 7860

# Single worker on purpose: the models are held in a per-process cache, and the
# free CPU tier has two cores that the Monte Carlo already saturates on its own.
CMD ["sh", "-c", "python -m uvicorn main:app --app-dir backend/app --host 0.0.0.0 --port ${PORT:-7860}"]
