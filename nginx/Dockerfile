FROM nginx:alpine

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

# Copy our config
COPY nginx.conf /etc/nginx/conf.d/edge_c2.conf

# SSL directory (certs mounted at runtime)
RUN mkdir -p /etc/nginx/ssl

EXPOSE 80 443
