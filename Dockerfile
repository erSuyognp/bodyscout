# Static BodyScout dashboard on nginx, for Cloud Run (see README, "Dashboard").
# Only the page and its data go in: no code, no .env, no API keys.
FROM nginx:1.27-alpine
ENV PORT=8080
COPY dashboard/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY dashboard/index.html /usr/share/nginx/html/dashboard/index.html
COPY runs/demo_blackboard.jsonl runs/demo_summary.json /usr/share/nginx/html/runs/
COPY results/bodies.csv results/bodies_meta.json results/learning.csv /usr/share/nginx/html/results/
EXPOSE 8080
