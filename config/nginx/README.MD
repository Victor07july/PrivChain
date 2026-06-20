# Configuração do NGinx

As configurações de redirecionamento e certificados, assim como o endereços dos containers aos quais o Nginx irá se conectar, estão todos definidos no arquivo `nginx.conf`

Atualmente os seguintes endpoints configurados para redirecionamento no container do Nginx:

1. `/admin/`: Redireciona todas as requisições para o backend de administração da rede Besu. Este backend é responsável por verificar se o usuário é administrador antes de executar qualquer alteração na rede, assim como se conecta direto com o nó RPC administrador da rede.
2. `/user/`: Repassa qualquer requisição para o nó RPC de usuário da rede Besu. Neste nó estão permitidos um conjunto limitado de ações, impedindo que o usuário altere configurações que possam afetar o funcionamento da rede.
3. `/`: A rota raiz do Nginx irá redirecionar para a aplicação Explorer da Rede Besu, permitindo observar, por exmeplo, os status da rede, nós conectados e blocos criados. A aplicação Explorer se conecta diretamente com o nó RPC de usuário, desta forma permitindo apenas um conjunto limitado de ações. 

O certificado autoassinado deve ser gerado no host e o mesmo será montado no container através de um bind. Para gerar um certificado autoassinado utilize os comandos a seguir a partir do diretório raiz do projeto starter:

# Criar diretório para os certificados
```sh
mkdir -p ./config/nginx/ssl
```

# Gerar o certificado autoassinado
```sh
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout ./config/nginx/ssl/nginx-selfsigned.key \
    -out ./config/nginx/ssl/nginx-selfsigned.crt \
    -subj "/C=BR/ST=SP/L=SaoPaulo/O=MyOrg/OU=IT/CN=localhost"
```