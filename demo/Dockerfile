FROM nginx:alpine

# Copy demo files to nginx html directory
COPY demo/ /usr/share/nginx/html/

# Copy custom nginx configuration if needed
# COPY demo/nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]