export const DATA_URL = "https://raw.githubusercontent.com/sbb2002/mewtype-schduler/data/schedule.json";
// For local development, temporarily comment out the line above and uncomment:
// export const DATA_URL = "../../fixtures/schedule.sample.json";

export const POLL_MS = 75000;
export const COUNTDOWN_TICK_MS = 60000;
export const FETCH_TIMEOUT_MS = 8000;

export const FALLBACK_CHANNEL_ORDER = ["arale", "yuno", "nonoka", "ritsu", "miyako"];

export const FALLBACK_CHANNELS = {
  arale: {
    name: "仲町あられ -Nakamachi Arale-",
    name_ko: "나카마치 아라레",
    channel_url: "https://www.youtube.com/@arale_yumemita"
  },
  yuno: {
    name: "千石ユノ -Sengoku Yuno-",
    name_ko: "센고쿠 유노",
    channel_url: "https://www.youtube.com/@yuno_yumemita"
  },
  nonoka: {
    name: "宮永ののか -Miyanaga Nonoka-",
    name_ko: "미야나가 노노카",
    channel_url: "https://www.youtube.com/@nonoka_yumemita"
  },
  ritsu: {
    name: "峰月律 -Minetsuki Ritsu-",
    name_ko: "미네츠키 리츠",
    channel_url: "https://www.youtube.com/@ritsu_yumemita"
  },
  miyako: {
    name: "藤都子 -Fuji Miyako-",
    name_ko: "후지 미야코",
    channel_url: "https://www.youtube.com/@miyako_yumemita"
  }
};
