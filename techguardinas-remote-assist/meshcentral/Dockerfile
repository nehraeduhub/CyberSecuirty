# Pinned, self-contained MeshCentral image for air-gapped operation.
# Build on a connected build host, then `docker save` the image into the MPLS environment.
FROM node:22-bookworm-slim
ARG MESHCENTRAL_VERSION=1.2.5
WORKDIR /opt/meshcentral
# Modules MeshCentral would otherwise try to `npm install` at first start are installed here at build time.
RUN npm install --omit=dev --no-audit --no-fund meshcentral@${MESHCENTRAL_VERSION} image-size@2.0.2 https-proxy-agent@7.0.6 \
 && npm cache clean --force
COPY render-config.js entrypoint.sh ./
RUN chmod +x entrypoint.sh && useradd --system --home /opt/meshcentral meshcentral \
 && mkdir -p meshcentral-data meshcentral-files meshcentral-backups meshcentral-recordings \
 && chown -R meshcentral:meshcentral /opt/meshcentral
USER meshcentral
EXPOSE 4430
ENTRYPOINT ["/opt/meshcentral/entrypoint.sh"]
