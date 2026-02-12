# 让国内可以访问：国内部署方案

Vercel 的服务器在海外，国内访问往往很慢或被限制。要让**国内用户**正常访问，需要把前端部署到国内可访问的环境，或通过国内节点加速。

---

## ⚠️ 关于 Gitee Pages

**Gitee Pages 已于 2024 年 5 月左右下线**，在「服务」里已无该选项，无法再使用。国内免备案的静态托管可改用下方 **Cloudflare Pages** 或 **腾讯云/阿里云**（需备案）等方案。项目内保留的 `frontend/deploy-gitee.sh` 仅适用于若将来 Gitee 恢复 Pages 或自建类似流程时使用。

---

## 方案对比（简要）

| 方案 | 国内访问 | 成本 | 难度 | 是否需要备案 |
|------|----------|------|------|----------------|
| 1. 腾讯云 / 阿里云 静态托管 | ✅ 好 | 有免费额度 | 中 | 使用国内节点需备案 |
| 2. 国内服务器 Nginx 反代 Vercel | ✅ 好 | 服务器月费 | 中高 | 需备案 |
| 3. Cloudflare Pages | ⚠️ 不稳定 | 免费 | 低 | 否（国内效果因地区而异） |

**推荐**：  
- **不想备案**：可试 **Cloudflare Pages**，国内部分地区能访问，但不保证稳定。  
- **可备案**：用 **腾讯云静态网站托管** 或 **阿里云 OSS + CDN**，稳定且快。

---

## 方案一：腾讯云静态网站托管（需备案，体验最好）⭐ 推荐

适合有域名且能备案的情况，国内访问速度和稳定性都较好。

1. **备案**
   - 在腾讯云完成 **ICP 备案**（需域名 + 国内服务器/托管产品）。

2. **开通静态网站托管**
   - 腾讯云 → **云开发** 或 **静态网站托管** 产品。
   - 创建环境，选择「静态网站托管」，按提示开通。

3. **构建并上传前端**
   - 本地：`cd frontend && npm run build`，得到 `frontend/dist`。
   - 在控制台把 `dist` 目录内所有文件上传到静态托管根目录（或按文档配置子目录）。

4. **绑定域名**
   - 在静态托管里绑定已备案的域名，并按提示解析（CNAME 等）。

5. **环境变量**
   - 若前端用 `VITE_API_BASE` 指向后端，需在**构建时**设置该变量再执行 `npm run build`，因为 Vite 会把环境变量打进构建产物。

国内用户访问你绑定的域名即可。

---

## 方案二：阿里云 OSS + CDN（需备案）

与腾讯云类似，用 OSS 存静态文件，CDN 加速：

1. 创建 OSS 桶，开启「静态页面」或配置索引页为 `index.html`。
2. 本地 `cd frontend && npm run build`，上传 `dist` 下所有文件到 OSS。
3. 开通 CDN，源站选该 OSS 桶，绑定已备案域名。
4. 前端若需请求自己的后端，同样在构建前设置 `VITE_API_BASE`。

---

## 方案三：国内服务器反代 Vercel（需一台国内机 + 备案）

保留 Vercel 部署不变，国内用户访问你的**国内域名**，由国内服务器转发到 Vercel，内容一致、国内可达。

### 第一步：准备服务器与域名备案

1. **购买国内云服务器**  
   腾讯云、阿里云、华为云等均可，地域选国内（如华北、华东），配置 1 核 1G 即可跑 Nginx 反代。记下**公网 IP**。

2. **准备域名并备案**  
   - 若还没有域名，在同一个云厂商买一个（备案会更快）。  
   - 在云控制台提交 **ICP 备案**，按指引完成（需身份证、手机号等，约几天到两周）。  
   - 备案通过后，在域名解析里添加 **A 记录**：主机记录 `@`（或 `www`），记录值填你的**服务器公网 IP**。

3. **确认 Vercel 访问地址**  
   在 Vercel 项目里找到当前部署的地址，形如：`https://shenlun-ai-xxxx.vercel.app`（或你绑定的自定义域名）。后面 Nginx 里的 `proxy_pass` 就填这个地址。

### 第二步：在服务器上安装 Nginx

SSH 登录服务器后执行（以 CentOS / 阿里云为例）：

```bash
# CentOS / 阿里云
sudo yum install -y nginx

# 若为 Ubuntu / Debian
# sudo apt update && sudo apt install -y nginx
```

启动并设置开机自启：

```bash
sudo systemctl start nginx
sudo systemctl enable nginx
```

### 第三步：写 Nginx 反代配置

1. 新建站点配置（把下面的 `你的国内域名` 和 `shenlun-ai-xxxx.vercel.app` 换成你自己的）：

```bash
sudo vim /etc/nginx/conf.d/shenlun.conf
```

2. 写入下面内容（**先只开 80 端口**，SSL 在下一步）：

```nginx
server {
    listen 80;
    server_name 你的国内域名;   # 例如 www.xxx.com 或 shenlun.xxx.com

    location / {
        proxy_pass https://shenlun-ai-xxxx.vercel.app;
        proxy_ssl_server_name on;
        proxy_set_header Host shenlun-ai-xxxx.vercel.app;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }
}
```

3. 检查配置并重载 Nginx：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

4. 浏览器访问 `http://你的国内域名`，应能打开和 Vercel 一样的页面。若打不开，检查：防火墙是否放行 80 端口、域名解析是否生效（`ping 你的国内域名` 是否指向服务器 IP）。

### 第四步：配置 HTTPS（推荐）

用 Let’s Encrypt 免费证书，在服务器上执行：

```bash
# CentOS 需先装 epel 再装 certbot
sudo yum install -y epel-release
sudo yum install -y certbot python3-certbot-nginx

# Ubuntu / Debian
# sudo apt install -y certbot python3-certbot-nginx

# 自动申请证书并让 certbot 修改 Nginx 配置（会帮你改成 443 并写好 ssl）
sudo certbot --nginx -d 你的国内域名
```

按提示输入邮箱、同意条款，完成后 certbot 会自动在 Nginx 里加上 443 和 `ssl_certificate` 等配置。

5. 再次重载 Nginx，用 `https://你的国内域名` 访问即可。

### 第五步：之后若 Vercel 地址变了

若你换了 Vercel 项目或域名，只需改 Nginx 里的两处：

- `proxy_pass https://新的vercel地址;`
- `proxy_set_header Host 新的vercel地址;`

然后执行 `sudo nginx -t && sudo systemctl reload nginx`。

### 说明

- **后端 API**：前端页面从国内经你服务器到 Vercel；页面里的接口请求（如批改）仍是浏览器直连你在前端里配置的后端（如 Render）。若后端在海外，国内请求接口可能仍会慢；若要把后端也放到国内，可再单独用 Nginx 反代后端或改前端的 `VITE_API_BASE` 指向国内后端。
- **防火墙**：云控制台安全组里需放行 **80** 和 **443** 端口。

---

## 方案四：Cloudflare Pages（免备案，国内效果因地区而异）

把前端部署到 Cloudflare Pages，有时国内能访问，但不稳定：

1. 在 [Cloudflare](https://dash.cloudflare.com) 选 **Pages** → 连接 GitHub，选本仓库。
2. 构建配置：根目录选 **`frontend`**，构建命令 **`npm run build`**，输出目录 **`dist`**。
3. 部署后得到 `xxx.pages.dev` 域名。

国内能否访问、速度如何，取决于当地网络，可作为免备案的备选尝试。

---

## 后端在国内的说明

若前端部署在国内，后端仍在海外（如 Render），国内用户请求批改接口会走国际网络，可能较慢或超时。

- **可选**：把后端也部署到**国内云**或**香港**服务器（如腾讯云、阿里云 ECS），在 frontend 里设置 `VITE_API_BASE` 指向该后端，国内访问会更快、更稳定。
- 若后端在国内且对公网提供 HTTPS，一般也需要备案（域名解析到国内 IP 时）。

---

## 总结

- **Gitee Pages 已下线**，无法再使用。  
- **有域名、可备案、追求国内体验**：用 **腾讯云静态托管** 或 **阿里云 OSS + CDN** 部署前端。  
- **已有 Vercel、不想改部署方式**：用 **国内服务器 Nginx 反代** Vercel，国内用户访问国内域名。  
- **不想备案、可接受不稳定**：可试 **Cloudflare Pages**，国内部分地区能访问。  
- 后端若也希望在国内快，可单独部署到国内/香港，并配置前端的 `VITE_API_BASE`。

当前项目 Vercel 的配置（见 `DEPLOY_VERCEL.md`）可保持不变，国内访问按上面任选一种方案即可。
