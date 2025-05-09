#!/bin/bash

# Substitua por seu domínio DuckDNS
domains=(apiwallet.duckdns.org auth.apiwallet.duckdns.org pgadmin.apiwallet.duckdns.org grafana.apiwallet.duckdns.org prometheus.apiwallet.duckdns.org)
rsa_key_size=4096
data_path="./certbot"
email="fredzolio@live.com"

# Função para criar conteúdo temporário para primeiro acesso
staging=0 # Set to 1 if testing on staging

if [ -d "$data_path" ]; then
  read -p "Certificados existentes encontrados. Continuar e substituir certificados existentes? (y/N) " decision
  if [ "$decision" != "Y" ] && [ "$decision" != "y" ]; then
    exit
  fi
fi

mkdir -p "$data_path/conf/live/$domains"

# Cria configurações padrão SSL
curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf > "$data_path/conf/options-ssl-nginx.conf"
curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot/certbot/ssl-dhparams.pem > "$data_path/conf/ssl-dhparams.pem"

echo "### Criando certificados temporários..."
for domain in "${domains[@]}"; do
  mkdir -p "$data_path/conf/live/$domain"
  
  # Gera certificados temporários
  openssl req -x509 -nodes -newkey rsa:$rsa_key_size -days 1 \
    -keyout "$data_path/conf/live/$domain/privkey.pem" \
    -out "$data_path/conf/live/$domain/fullchain.pem" \
    -subj "/CN=localhost"
done

echo "### Iniciando nginx..."
docker compose up --force-recreate -d nginx
echo

# Solicita certificados reais
for domain in "${domains[@]}"; do
  echo "### Solicitando Let's Encrypt para $domain..."
  
  # Select appropriate EMAIL and DOMAIN flags
  domain_arg="-d $domain"
  
  # Habilita staging mode se necessário
  if [ $staging != "0" ]; then 
    staging_arg="--staging"; 
  fi

  docker compose run --rm --entrypoint "\
    certbot certonly --webroot -w /var/www/certbot \
      $staging_arg \
      --email $email \
      --agree-tos \
      --no-eff-email \
      --force-renewal \
      $domain_arg \
  " certbot
  echo
done

echo "### Reiniciando nginx..."
docker compose exec nginx nginx -s reload 