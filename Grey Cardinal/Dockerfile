# Production image for the Grey Cardinal marketing+cockpit site (static HTML/CSS,
# React + Babel transpiled in-browser from unpkg). Served by nginx behind Caddy.
FROM nginx:alpine
COPY . /usr/share/nginx/html
# Entry file has a space in its name; expose it as index.html and drop build files.
RUN cp "/usr/share/nginx/html/Grey Cardinal.html" /usr/share/nginx/html/index.html \
    && rm -f /usr/share/nginx/html/Dockerfile /usr/share/nginx/html/nginx.conf /usr/share/nginx/html/.dockerignore
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
