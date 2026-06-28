# 在官方 ES 镜像上装 ik 中文分词插件，版本号必须与 ES 主版本完全一致。
ARG ES_VERSION=8.17.6
FROM docker.elastic.co/elasticsearch/elasticsearch:${ES_VERSION}

# ik 版本号要和 ES_VERSION 一一对应，否则插件加载会报错。
ARG ES_VERSION
RUN bin/elasticsearch-plugin install --batch \
    "https://get.infini.cloud/elasticsearch/analysis-ik/${ES_VERSION}"
