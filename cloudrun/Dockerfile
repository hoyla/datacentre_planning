# Datacentre reader — Cloud Run service. A single self-contained index.html
# served by nginx, precompressed at build time (the page runs to ~17MB raw;
# gzip_static serves the .gz to every modern browser). Private service; IAP
# gates at the Cloud Run edge (see CLOUDRUN.md) so nginx serves open inside
# the perimeter, exactly as the tribunal Datasette and meridian portal do.
FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html robots.txt /usr/share/nginx/html/
RUN gzip -9k /usr/share/nginx/html/index.html
