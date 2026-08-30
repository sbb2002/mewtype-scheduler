export const DATA_URL = "https://raw.githubusercontent.com/sbb2002/mewtype-scheduler/data/schedule.json";
// For local development, temporarily comment out the line above and uncomment:
// export const DATA_URL = "../../fixtures/schedule.sample.json";

export const POLL_MS = 75000;
export const COUNTDOWN_TICK_MS = 60000;
export const FETCH_TIMEOUT_MS = 8000;

export const FALLBACK_CHANNEL_ORDER = ["arale", "yuno", "nonoka", "ritsu", "miyako"];

// schedule.json 의 channels[key] 에 빠진 필드(예: 아직 수집 안 된 avatar)를
// render.js 가 이 값으로 필드 단위 보강한다. avatar 는 s176 로 정규화된 yt3 URL.
export const FALLBACK_CHANNELS = {
  arale: {
    name: "仲町あられ -Nakamachi Arale-",
    name_ko: "나카마치 아라레",
    handle: "arale_yumemita",
    channel_url: "https://www.youtube.com/@arale_yumemita",
    avatar: "https://yt3.googleusercontent.com/I0mwftAJiprbJyaBo_1UwcLlO1iWJvinlMdEQ3RlLQutvqZ0PRFH4Oyw1p1zHxRTp5QyAvLNkg8=s176-c-k-c0x00ffffff-no-rj"
  },
  yuno: {
    name: "千石ユノ -Sengoku Yuno-",
    name_ko: "센고쿠 유노",
    handle: "yuno_yumemita",
    channel_url: "https://www.youtube.com/@yuno_yumemita",
    avatar: "https://yt3.googleusercontent.com/r9DwFMzCr4Df7o52ZpNgVvPlAdUD4wwsCbkhhyJTlGUCodEKQMH7axWtJf42bxo-5-M6HOwX0w=s176-c-k-c0x00ffffff-no-rj"
  },
  nonoka: {
    name: "宮永ののか -Miyanaga Nonoka-",
    name_ko: "미야나가 노노카",
    handle: "nonoka_yumemita",
    channel_url: "https://www.youtube.com/@nonoka_yumemita",
    avatar: "https://yt3.googleusercontent.com/nZ3SFdbhOcw4_GrJ3kUvQ98Oss8usOumquIRHOMrhdFWWAxiPkgRYXQA4TTnH8y6uUy6wLE0=s176-c-k-c0x00ffffff-no-rj"
  },
  ritsu: {
    name: "峰月律 -Minetsuki Ritsu-",
    name_ko: "미네츠키 리츠",
    handle: "ritsu_yumemita",
    channel_url: "https://www.youtube.com/@ritsu_yumemita",
    avatar: "https://yt3.googleusercontent.com/UD-po-IezRUMR-_k_Rgl9APp-W-CZfNEv1b3BJyztb4W_D6EJfeflpfEd9l3FekTbrEgg2Pi=s176-c-k-c0x00ffffff-no-rj"
  },
  miyako: {
    name: "藤都子 -Fuji Miyako-",
    name_ko: "후지 미야코",
    handle: "miyako_yumemita",
    channel_url: "https://www.youtube.com/@miyako_yumemita",
    avatar: "https://yt3.googleusercontent.com/qsuSTaNiWOw_ddYcMRiHbSawpbhfVpKrwGnffmXBpEikilgiBfxOlZmlBlUu5de0r9McYYLo=s176-c-k-c0x00ffffff-no-rj"
  }
};
