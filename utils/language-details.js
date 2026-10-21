module.exports = [
  {
    "name": "中文",
    "code": "ZH",
    "locale": "zh-CN",
    "metrics": [
      {
        "key": "semantic",
        "label": "语义相似度",
        "value": "0.97",
        "threshold": "阈值 ≥ 0.85",
        "pass": true
      },
      {
        "key": "terms",
        "label": "术语覆盖率",
        "value": "98.3%",
        "threshold": "阈值 ≥ 90%",
        "pass": true
      },
      {
        "key": "exact",
        "label": "公式/数字/专名",
        "value": "100.0%",
        "threshold": "逐项精确匹配",
        "pass": true
      },
      {
        "key": "llm",
        "label": "整体语义校验",
        "value": "通过",
        "threshold": "上下文一致性判断",
        "pass": true
      }
    ],
    "samples": [
      {
        "page": 1,
        "source": "Let's officially enter our study of this course. In the first chapter, we will mainly learn an overview of artificial intelligence. We will introduce it from several aspects. First and foremost, the origin and general introduction to artificial intelligence.",
        "translated": "让我们正式开始学习本课程。在第一章中，我们将主要学习人工智能概述。我们将从多个方面进行介绍。首先也是最重要的是，人工智能的起源与总体介绍。",
        "backTranslated": "Let us formally begin studying this course. In Chapter 1, we will mainly study an overview of artificial intelligence. We will introduce it from multiple aspects. First and most importantly, the origins of artificial intelligence and a general introduction.",
        "report": "Faithful translation; tone and structure match the source. Key terms like 'artificial intelligence' and 'overview' are correctly rendered."
      },
      {
        "page": 2,
        "source": "Here is the content of this chapter.",
        "translated": "下面是本章的内容。",
        "backTranslated": "Below is the content of this chapter.",
        "report": "Direct and accurate; no terminology or naming issues."
      },
      {
        "page": 3,
        "source": "now lets discusss 1.1 Origins and Fundamentals of Artificial Intelligence",
        "translated": "现在让我们讨论 1.1 人工智能的起源与基础。",
        "backTranslated": "Now let's discuss 1.1 The origins and foundations of artificial intelligence.",
        "report": "Meaning is preserved; 'Origins and Fundamentals' is well conveyed as '起源与基础'. Section number 1.1 is preserved."
      }
    ],
    "passed": true
  },
  {
    "name": "英语",
    "code": "EN",
    "locale": "en-US",
    "metrics": [
      {
        "key": "semantic",
        "label": "语义相似度",
        "value": "1.00",
        "threshold": "阈值 ≥ 0.85",
        "pass": true
      },
      {
        "key": "terms",
        "label": "术语覆盖率",
        "value": "100.0%",
        "threshold": "阈值 ≥ 90%",
        "pass": true
      },
      {
        "key": "exact",
        "label": "公式/数字/专名",
        "value": "100.0%",
        "threshold": "逐项精确匹配",
        "pass": true
      },
      {
        "key": "llm",
        "label": "整体语义校验",
        "value": "通过",
        "threshold": "上下文一致性判断",
        "pass": true
      }
    ],
    "samples": [
      {
        "page": 1,
        "source": "Let's officially enter our study of this course. In the first chapter, we will mainly learn an overview of artificial intelligence. We will introduce it from several aspects. First and foremost, the origin and general introduction to artificial intelligence.",
        "translated": "Let's officially enter our study of this course. In the first chapter, we will mainly learn an overview of artificial intelligence. We will introduce it from several aspects. First and foremost, the origin and general introduction to artificial intelligence.",
        "backTranslated": "Let's officially enter our study of this course. In the first chapter, we will mainly learn an overview of artificial intelligence. We will introduce it from several aspects. First and foremost, the origin and general introduction to artificial intelligence.",
        "report": "四项校验均通过。"
      },
      {
        "page": 2,
        "source": "Here is the content of this chapter.",
        "translated": "Here is the content of this chapter.",
        "backTranslated": "Here is the content of this chapter.",
        "report": "四项校验均通过。"
      },
      {
        "page": 3,
        "source": "now lets discusss 1.1 Origins and Fundamentals of Artificial Intelligence",
        "translated": "now lets discusss 1.1 Origins and Fundamentals of Artificial Intelligence",
        "backTranslated": "now lets discusss 1.1 Origins and Fundamentals of Artificial Intelligence",
        "report": "四项校验均通过。"
      }
    ],
    "passed": true
  },
  {
    "name": "日语",
    "code": "JA",
    "locale": "ja-JP",
    "metrics": [
      {
        "key": "semantic",
        "label": "语义相似度",
        "value": "0.97",
        "threshold": "阈值 ≥ 0.85",
        "pass": true
      },
      {
        "key": "terms",
        "label": "术语覆盖率",
        "value": "95.3%",
        "threshold": "阈值 ≥ 90%",
        "pass": true
      },
      {
        "key": "exact",
        "label": "公式/数字/专名",
        "value": "100.0%",
        "threshold": "逐项精确匹配",
        "pass": true
      },
      {
        "key": "llm",
        "label": "整体语义校验",
        "value": "通过",
        "threshold": "上下文一致性判断",
        "pass": true
      }
    ],
    "samples": [
      {
        "page": 1,
        "source": "Let's officially enter our study of this course. In the first chapter, we will mainly learn an overview of artificial intelligence. We will introduce it from several aspects. First and foremost, the origin and general introduction to artificial intelligence.",
        "translated": "それでは、本講義の学習を正式に開始しましょう。第1章では、主として人工知能の概観を学びます。複数の側面から紹介していきます。まず第一に、人工知能の起源と一般的な導入です。",
        "backTranslated": "Now, let’s officially begin studying this course. In Chapter 1, we will mainly learn an overview of artificial intelligence. We will introduce it from multiple aspects. First of all, the origins of artificial intelligence and a general introduction.",
        "report": "Faithful rendering of meaning and structure; key terms like 'artificial intelligence', 'overview', and 'origin' are correctly conveyed."
      },
      {
        "page": 2,
        "source": "Here is the content of this chapter.",
        "translated": "以下が本章の内容です。",
        "backTranslated": "Below is the content of this chapter.",
        "report": "Accurate and natural; matches the source intent precisely."
      },
      {
        "page": 3,
        "source": "now lets discusss 1.1 Origins and Fundamentals of Artificial Intelligence",
        "translated": "それでは、1.1 人工知能の起源と基礎 について議論しましょう。",
        "backTranslated": "Now, let’s discuss 1.1 Origins and Fundamentals of Artificial Intelligence.",
        "report": "Section number '1.1' preserved; 'origins' and 'fundamentals/basics' correctly translated as '起源と基礎'."
      }
    ],
    "passed": true
  },
  {
    "name": "韩语",
    "code": "KO",
    "locale": "ko-KR",
    "metrics": [
      {
        "key": "semantic",
        "label": "语义相似度",
        "value": "0.98",
        "threshold": "阈值 ≥ 0.85",
        "pass": true
      },
      {
        "key": "terms",
        "label": "术语覆盖率",
        "value": "97.7%",
        "threshold": "阈值 ≥ 90%",
        "pass": true
      },
      {
        "key": "exact",
        "label": "公式/数字/专名",
        "value": "100.0%",
        "threshold": "逐项精确匹配",
        "pass": true
      },
      {
        "key": "llm",
        "label": "整体语义校验",
        "value": "通过",
        "threshold": "上下文一致性判断",
        "pass": true
      }
    ],
    "samples": [
      {
        "page": 1,
        "source": "Let's officially enter our study of this course. In the first chapter, we will mainly learn an overview of artificial intelligence. We will introduce it from several aspects. First and foremost, the origin and general introduction to artificial intelligence.",
        "translated": "이제 본 강의의 학습을 공식적으로 시작하겠습니다. 첫 번째 장에서는 인공지능의 개요를 주로 학습할 것입니다. 여러 측면에서 소개하겠습니다. 무엇보다도 인공지능의 기원과 일반적 소개부터 다루겠습니다.",
        "backTranslated": "Now, we will officially begin studying this course. In the first chapter, we will mainly learn an overview of artificial intelligence. We will introduce it from several aspects. Above all, we will cover the origin and general introduction of artificial intelligence first.",
        "report": "Meaning and structure are preserved; terminology like 'artificial intelligence' and 'overview' is correctly rendered."
      },
      {
        "page": 2,
        "source": "Here is the content of this chapter.",
        "translated": "다음은 이 장의 내용입니다.",
        "backTranslated": "The following is the content of this chapter.",
        "report": "Accurate and natural Korean; no terminology loss."
      },
      {
        "page": 3,
        "source": "now lets discusss 1.1 Origins and Fundamentals of Artificial Intelligence",
        "translated": "이제 1.1 인공지능의 기원과 기초를 논의하겠습니다.",
        "backTranslated": "Now, we will discuss 1.1 the origins and basics of artificial intelligence.",
        "report": "Section number '1.1' preserved; 'Origins and Fundamentals' appropriately translated as '기원과 기초'."
      }
    ],
    "passed": true
  },
  {
    "name": "德语",
    "code": "DE",
    "locale": "de-DE",
    "metrics": [
      {
        "key": "semantic",
        "label": "语义相似度",
        "value": "0.97",
        "threshold": "阈值 ≥ 0.85",
        "pass": true
      },
      {
        "key": "terms",
        "label": "术语覆盖率",
        "value": "96.7%",
        "threshold": "阈值 ≥ 90%",
        "pass": true
      },
      {
        "key": "exact",
        "label": "公式/数字/专名",
        "value": "100.0%",
        "threshold": "逐项精确匹配",
        "pass": true
      },
      {
        "key": "llm",
        "label": "整体语义校验",
        "value": "通过",
        "threshold": "上下文一致性判断",
        "pass": true
      }
    ],
    "samples": [
      {
        "page": 1,
        "source": "Let's officially enter our study of this course. In the first chapter, we will mainly learn an overview of artificial intelligence. We will introduce it from several aspects. First and foremost, the origin and general introduction to artificial intelligence.",
        "translated": "Beginnen wir nun offiziell mit der Bearbeitung dieses Kurses. Im ersten Kapitel lernen wir hauptsächlich einen Überblick über künstliche Intelligenz kennen. Wir werden sie aus mehreren Perspektiven vorstellen. An erster Stelle stehen die Ursprünge und eine allgemeine Einführung in die künstliche Intelligenz.",
        "backTranslated": "Let us now officially begin working on this course. In the first chapter, we will mainly learn an overview of artificial intelligence. We will present it from several perspectives. First and foremost are the origins and a general introduction to artificial intelligence.",
        "report": "Meaning preserved; minor stylistic shift ('Bearbeitung' vs. 'study') without semantic loss."
      },
      {
        "page": 2,
        "source": "Here is the content of this chapter.",
        "translated": "Hier ist der Inhalt dieses Kapitels.",
        "backTranslated": "Here is the content of this chapter.",
        "report": "Direct and accurate translation."
      },
      {
        "page": 3,
        "source": "now lets discusss 1.1 Origins and Fundamentals of Artificial Intelligence",
        "translated": "Lassen Sie uns nun 1.1 Ursprünge und Grundlagen der Künstlichen Intelligenz besprechen",
        "backTranslated": "Let us now discuss 1.1 origins and fundamentals of artificial intelligence.",
        "report": "Accurate rendering; section number 1.1 preserved. Minor capitalization issue ('Künstlichen') is non-critical."
      }
    ],
    "passed": true
  },
  {
    "name": "法语",
    "code": "FR",
    "locale": "fr-FR",
    "metrics": [
      {
        "key": "semantic",
        "label": "语义相似度",
        "value": "0.98",
        "threshold": "阈值 ≥ 0.85",
        "pass": true
      },
      {
        "key": "terms",
        "label": "术语覆盖率",
        "value": "100.0%",
        "threshold": "阈值 ≥ 90%",
        "pass": true
      },
      {
        "key": "exact",
        "label": "公式/数字/专名",
        "value": "100.0%",
        "threshold": "逐项精确匹配",
        "pass": true
      },
      {
        "key": "llm",
        "label": "整体语义校验",
        "value": "通过",
        "threshold": "上下文一致性判断",
        "pass": true
      }
    ],
    "samples": [
      {
        "page": 1,
        "source": "Let's officially enter our study of this course. In the first chapter, we will mainly learn an overview of artificial intelligence. We will introduce it from several aspects. First and foremost, the origin and general introduction to artificial intelligence.",
        "translated": "Entrons officiellement dans l’étude de ce cours. Dans le premier chapitre, nous apprendrons principalement une vue d’ensemble de l’intelligence artificielle. Nous l’introduirons sous plusieurs aspects. Avant tout, l’origine et l’introduction générale à l’intelligence artificielle.",
        "backTranslated": "Let’s officially begin our study of this course. In the first chapter, we will mainly learn an overview of artificial intelligence. We will introduce it from several aspects. First and foremost, the origin and the general introduction to artificial intelligence.",
        "report": "Faithful rendering; terminology for 'artificial intelligence' consistent and accurate."
      },
      {
        "page": 2,
        "source": "Here is the content of this chapter.",
        "translated": "Voici le contenu de ce chapitre.",
        "backTranslated": "Here is the content of this chapter.",
        "report": "Exact and natural translation."
      },
      {
        "page": 3,
        "source": "now lets discusss 1.1 Origins and Fundamentals of Artificial Intelligence",
        "translated": "Discutons maintenant de 1.1 Origines et fondements de l’intelligence artificielle.",
        "backTranslated": "Let’s now discuss 1.1 Origins and foundations of artificial intelligence.",
        "report": "Meaning preserved; section number '1.1' correctly retained; terminology consistent."
      }
    ],
    "passed": true
  }
]
