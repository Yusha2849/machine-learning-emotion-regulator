import os
import pandas as pd
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk import NaiveBayesClassifier

class NLP:
    classifier = None
    stop_words = None

    @staticmethod
    def setup():
        print("Setting up")

        NLP._ensure_nltk_data()
        NLP.stop_words = set(stopwords.words('english'))

        file_path = os.path.join(os.path.dirname(__file__), '../static/trainingdata.csv')
        df = pd.read_csv(file_path)
        train_data = [(row['sentence'], row['emotion']) for _, row in df.iterrows()]
        train_set = [(NLP._extract_features(NLP._preprocess(sentence)), emotion) for (sentence, emotion) in train_data]
        NLP.classifier = NaiveBayesClassifier.train(train_set)
        print("Setup")

    @staticmethod
    def _ensure_nltk_data():
        resources = [
            ('tokenizers/punkt', 'punkt'),
            ('corpora/stopwords', 'stopwords'),
            ('tokenizers/punkt_tab','punkt_tab' )
        ]

        for resource_path, resource_name in resources:
            try:
                nltk.data.find(resource_path)
                print(f"{resource_name} here")
            except LookupError:
                print(f"{resource_name} Downloading, park")
                nltk.download(resource_name, quiet=True)
                print(f"{resource_name} Kla and setup")
        

    @staticmethod
    def operate(sentence):
        if NLP.classifier is None:
            raise RuntimeError("You stupid, run setup first")
        return NLP._predict_emotion(sentence)

    @staticmethod
    def _preprocess(sentence):
        words = word_tokenize(sentence.lower())
        return [word for word in words if word.isalnum() and word not in NLP.stop_words]

    @staticmethod
    def _extract_features(words):
        return {word: True for word in words}

    @staticmethod
    def _predict_emotion(sentence):
        features = NLP._extract_features(NLP._preprocess(sentence))
        return NLP.classifier.classify(features)
