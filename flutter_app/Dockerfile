# Pinned to match .github/workflows/flutter-ci.yml -- "stable" has moved past
# APIs this app depends on (e.g. CupertinoPageTransitionsBuilder removal).
FROM ghcr.io/cirruslabs/flutter:3.41.2 AS build
WORKDIR /app

COPY pubspec.yaml pubspec.lock ./
RUN flutter pub get

COPY . .

ARG API_BASE_URL=http://localhost:8000
RUN flutter build web --release --dart-define=API_BASE_URL=${API_BASE_URL}

FROM nginx:alpine
COPY --from=build /app/build/web /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
