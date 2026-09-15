FROM mcr.microsoft.com/azure-functions/node:4-node20

RUN apt-get update && \
    apt-get install -y ghostscript fonts-nanum && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN ln -s /usr/share/fonts/truetype/nanum /usr/share/ghostscript/fonts/

COPY . /home/site/wwwroot
RUN cd /home/site/wwwroot && npm install
