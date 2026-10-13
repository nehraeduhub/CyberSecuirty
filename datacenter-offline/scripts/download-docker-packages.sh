#!/usr/bin/env bash
# Download Docker Engine + compose plugin packages, with dependencies, for an
# OFFLINE server, as a small local package repository.
# Runs on the online machine (needs Docker); called by prepare-offline-bundle.sh.
#
#   ./download-docker-packages.sh <target> <output-dir>
#
#   target: ubuntu:24.04 | ubuntu:22.04 | debian:12 | rockylinux:9 | almalinux:9
#           (RHEL 9 servers: use rockylinux:9 or almalinux:9)
#
# Optional: UBUNTU_MIRROR / DEBIAN_MIRROR (e.g. your internal mirror URL)
set -euo pipefail

TARGET=${1:?usage: $0 <target> <output-dir>}
OUT=${2:?usage: $0 <target> <output-dir>}
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
PKGS="docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"

# Pass the host's proxy settings through, if any
proxy_env=()
for v in http_proxy https_proxy no_proxy HTTP_PROXY HTTPS_PROXY NO_PROXY; do
  [ -n "${!v:-}" ] && proxy_env+=(-e "$v=${!v}")
done

run() { # image script
  docker run --rm --network host --platform linux/amd64 "${proxy_env[@]}" \
    -v "$OUT:/out" -v /etc/ssl/certs:/etc/ssl/certs:ro \
    -e UBUNTU_MIRROR="${UBUNTU_MIRROR:-}" -e DEBIAN_MIRROR="${DEBIAN_MIRROR:-}" \
    -e PKGS="$PKGS" "$1" bash -ec "$2"
}

case "$TARGET" in
  ubuntu:*|debian:*)
    curl -fsSL "https://download.docker.com/linux/${TARGET%%:*}/gpg" -o "$OUT/docker.asc"
    # 1) In a clean image: only Docker's packages and what they need beyond a base system
    run "$TARGET" '
      export DEBIAN_FRONTEND=noninteractive
      . /etc/os-release
      if [ -n "$UBUNTU_MIRROR" ] && [ "$ID" = ubuntu ]; then
        sed -i "s#http://archive.ubuntu.com/ubuntu#$UBUNTU_MIRROR#; s#http://security.ubuntu.com/ubuntu#$UBUNTU_MIRROR#" /etc/apt/sources.list.d/ubuntu.sources
      fi
      if [ -n "$DEBIAN_MIRROR" ] && [ "$ID" = debian ]; then
        sed -i "s#http://deb.debian.org/debian#$DEBIAN_MIRROR#" /etc/apt/sources.list.d/debian.sources
      fi
      echo "deb [arch=amd64 signed-by=/out/docker.asc] https://download.docker.com/linux/$ID $VERSION_CODENAME stable" \
        > /etc/apt/sources.list.d/docker.list
      apt-get update -qq
      apt-get install -y -qq --no-install-recommends --download-only $PKGS iptables >/dev/null
      cp /var/cache/apt/archives/*.deb /out/
      echo "$ID $VERSION_ID" > /out/TARGET
    '
    # 2) Index them so apt can use the folder as a repository
    run "$TARGET" '
      export DEBIAN_FRONTEND=noninteractive
      . /etc/os-release
      if [ -n "$UBUNTU_MIRROR" ] && [ "$ID" = ubuntu ]; then
        sed -i "s#http://archive.ubuntu.com/ubuntu#$UBUNTU_MIRROR#; s#http://security.ubuntu.com/ubuntu#$UBUNTU_MIRROR#" /etc/apt/sources.list.d/ubuntu.sources
      fi
      apt-get update -qq && apt-get install -y -qq dpkg-dev >/dev/null
      cd /out && dpkg-scanpackages --multiversion . /dev/null 2>/dev/null > Packages && gzip -kf Packages
    '
    rm -f "$OUT/docker.asc"
    ;;
  rockylinux:*|almalinux:*)
    run "$TARGET" '
      dnf -y -q install dnf-plugins-core createrepo_c >/dev/null
      dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
      dnf -y -q download --resolve --alldeps --destdir /out $PKGS iptables-nft
      createrepo_c -q /out
      . /etc/os-release; echo "$ID $VERSION_ID" > /out/TARGET
    '
    ;;
  *)
    echo "Unsupported target '$TARGET'. Use ubuntu:24.04, ubuntu:22.04, debian:12, rockylinux:9 or almalinux:9." >&2
    exit 1 ;;
esac

echo "Docker packages for $TARGET in $OUT: $(find "$OUT" -name '*.deb' -o -name '*.rpm' | wc -l) package(s), $(du -sh "$OUT" | cut -f1)"
