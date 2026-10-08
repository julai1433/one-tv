# Ubuntu 24.04 con PowerShell 7 (pwsh) y Python, para revisar los guiones de Windows sin Windows: que se lean sin
# errores y que los del firewall (mac/winfirewall.py) hagan lo que deben, con los comandos de Windows reemplazados por
# unos falsos. Lo usa pruebas/powershell.sh.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 POWERSHELL_TELEMETRY_OPTOUT=1
ARG PWSH=7.6.6
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && case "$(dpkg --print-architecture)" in arm64) a=arm64 ;; *) a=x64 ;; esac \
 && curl -fsSL -o /tmp/pwsh.tar.gz "https://github.com/PowerShell/PowerShell/releases/download/v$PWSH/powershell-$PWSH-linux-$a.tar.gz" \
 && mkdir -p /opt/pwsh && tar -xzf /tmp/pwsh.tar.gz -C /opt/pwsh && rm /tmp/pwsh.tar.gz \
 && chmod +x /opt/pwsh/pwsh && ln -s /opt/pwsh/pwsh /usr/local/bin/pwsh
RUN useradd -m prueba
USER prueba
WORKDIR /home/prueba
