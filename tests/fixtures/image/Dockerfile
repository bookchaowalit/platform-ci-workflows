# Self-test fixture for image-scan.yml: a small base image, patched at build time, non-root.
FROM docker.io/library/alpine:3.20
RUN apk upgrade --no-cache && echo "image-scan self-test" > /hello.txt
USER nobody
CMD ["cat", "/hello.txt"]
