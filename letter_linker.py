#Letter Linker
#Aboudi Rai, 2019

import logging
import json
import random

from ask_sdk.standard import StandardSkillBuilder
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.skill_builder import CustomSkillBuilder
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response, IntentRequest
from ask_sdk_model.interfaces.audioplayer import (
    PlayDirective, PlayBehavior, AudioItem, Stream)
from ask_sdk_model.services.monetization import (
    EntitledState, PurchasableState, InSkillProductsResponse, Error, 
    InSkillProduct)
from ask_sdk_model.interfaces.monetization.v1 import PurchaseResult
from ask_sdk_model.interfaces.connections import SendRequestDirective
import boto3
import ask_sdk_dynamodb

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

skill_name = "Letter Linker"

starter_text = ("Try and beat your high score of {} points. Say any word that begins with the last letter of my word. My word is, {}.")
moreTimeText = "If you need more time, say 'I need more time'."
noTimeText = " Times up. That's the end of this letter link. If you want to use an extra life to continue, say 'use extra life'. If you want to play again, say 'play letter linker'. If you want to exit the game, say 'exit game'. " 
help_text2 = "It's simple! Just say a word that begins with the last letter of my word, which is, {}"
help_text = ("Letter Linker is simple. Continue the letter link by saying a word that begins with the last letter of my word, and then I will do the same. No repeats are allowed. You'll receive a score and a linker rank at the end of your link! If you ever want to end the letter link, just say, exit game. Say any word that begins with the last letter of my word. My word is, {}.")
word_slot_key = "currWord"
word_slot = "currWord"

ranks = {"0" : "Novice",
        "500": "White Belt",
        "1000": "Yellow Belt",
        "1500": "Orange Belt",
        "2000": "Purple Belt",
        "2500": "Blue Belt",
        "3000": "Green Belt",
        "3500": "Advanced Green Belt",
        "4000": "Brown Belt",
        "4500": "Advanced Brown Belt",
        "5000": "Black Belt"}

rank = "Novice"

SKILL_NAME = 'Letter Linker'

sb = StandardSkillBuilder(table_name="LetterLinker", auto_create_table=True)

alexaWord = ""
category = ""
category_data = []
scoreInitial = 0
scoreIncrement = 100

def in_skill_product_response(handler_input):
    locale = handler_input.request_envelope.request.locale
    ms = handler_input.service_client_factory.get_monetization_service()
    return ms.get_in_skill_products(locale)

#Function that takes file and returns array of clean data
def jsonToArray(filename):
    with open(filename, 'r') as f:
        temp = json.load(f)
    arr = temp.values()
    clean_arr = []
    for i in arr:
        for j in i:
            name = j.get("name")
            if(name != None):
                clean_arr.append(name.lower())

    return clean_arr

#txt file to array
def txtToArray(filename):
    clean_arr = []
    with open(filename) as file:
        for line in file.readlines():
            clean_arr.append(line.strip())
    return clean_arr

def continuedGame(handler_input):   
    attr = handler_input.attributes_manager.session_attributes
    persAttr = handler_input.attributes_manager.persistent_attributes

    #grabbing relevant persistent attributes
    attr["score"] = persAttr["score"]
    attr["used_words"] = persAttr["used_words"]
    attr["category_data"] = persAttr["category_data"]
    attr["rank"] = persAttr["rank"]
    speech = ""

    foundOne = False
    for i in range(len(attr["category_data"])):
        newChoice = random.choice(attr["category_data"])
        if newChoice not in attr["used_words"]:
            attr["alexaWord"] = newChoice
            foundOne = True
            break
    
    #checking if alexa found a word, if not the user wins
    if not foundOne:
        speech = ("Hmm. I can't think of a word. You win this time. Your final score was {}. I'll award you with a free extra life for winning.").format(attr["score"])
        persAttr["lives"] += 1 #adding life because alexa lost
        
        handler_input.attributes_manager.save_persistent_attributes()   

        handler_input.response_builder.set_should_end_session(True)
    else:
        newAlexaWord = attr["alexaWord"]
        attr["used_words"].append(newAlexaWord)
        
        speech = ("Alright, let's keep the letter link going. Your score is {}. My next word is, {}").format(attr["score"], newAlexaWord)
        attr["responded"] = False

    handler_input.response_builder.speak(speech).ask(noTimeText)
    return handler_input.response_builder.response

def endGame(handler_input):
    attr = handler_input.attributes_manager.session_attributes
    persAttr = handler_input.attributes_manager.persistent_attributes
     
    attr["score"] = persAttr["score"]
    attr["rank"] = persAttr["rank"]    
    
    speech = ("Thanks for playing!")
    
    if persAttr["highscore"] < attr["score"]:
            persAttr["highscore"] = attr["score"]
            speech += " You've reached a new high score of {}!".format(attr["score"])
    elif persAttr["highscore"] == attr["score"]:
        speech += " You've tied your high score of {}!".format(attr["score"])
    else:
        speech += " You had {} points, only {} away from your high score!".format(attr["score"], persAttr["highscore"] - attr["score"])
    
    #setting new ranks
    rankKeys = list(ranks)
    for i in range(1, len(rankKeys) - 1):
        if persAttr["highscore"] >= int(rankKeys[i - 1]) and persAttr["highscore"] < int(rankKeys[i]):
            if attr["rank"] == ranks[rankKeys[i - 1]]:
                speech += " Your linker rank is, {}.".format(attr["rank"])
            else:
                attr["rank"] = ranks[rankKeys[i - 1]]
                speech += " You've achieved the new linker rank, {}.".format(attr["rank"])
    if persAttr["highscore"] >= int(rankKeys[len(rankKeys) - 1]):
        if attr["rank"] == ranks[rankKeys[len(rankKeys) - 1]]:
                speech += " Your linker rank is, {}.".format(attr["rank"])
        else:
            attr["rank"] = ranks[rankKeys[len(rankKeys) - 1]]
            speech += " You've achieved the new linker rank, {}.".format(attr["rank"])

    speech += " Play again soon!"

    persAttr["rank"] = attr["rank"]
    
    handler_input.attributes_manager.save_persistent_attributes()

    handler_input.response_builder.speak(speech).ask(speech)
    handler_input.response_builder.set_should_end_session(True)
    return handler_input.response_builder.response

#you may need to check whether the user has refunded their lives
@sb.request_handler(can_handle_func = is_request_type("LaunchRequest"))
def launch_request_handler(handler_input):
    
    speech = "Welcome to Letter Linker."
    category_data = jsonToArray("wordList.json")
    usedWords = []
    attr = handler_input.attributes_manager.session_attributes
    persAttr = handler_input.attributes_manager.persistent_attributes
    
    livesInitial = 1

    #intiating list with rare words starting with x, y, and z
    wordSubList = category_data[len(category_data) - 245:len(category_data) - 1]
    
    #CONSIDER FILLING ALEXA ATTRIBUTES WITH ALL THE WORDS
    i = 0
    while i < 1000:
        word = random.choice(category_data)
        #limiting number of common letter endings
        if word not in wordSubList:
            if word[len(word) - 1] == "s":
                if random.randint(1, 1000) == 2:
                    wordSubList.append(word)
                    i+=1
            elif word[len(word) - 1] == "g":
                if random.randint(1, 900) == 2:
                    wordSubList.append(word)
                    i+=1
            elif word[len(word) - 1] == "d":
                if random.randint(1, 600) == 2:
                    wordSubList.append(word)
                    i+=1
            elif word[len(word) - 1] == "y":
                if random.randint(1, 500) == 2:
                    wordSubList.append(word)
                    i+=1
            elif word[len(word) - 1] == "e":
                if random.randint(1, 50) == 2:
                    wordSubList.append(word)
                    i+=1
            else:
                wordSubList.append(word)
                i+=1

    
    #if its first time save the "highscore" key
    if "highscore" not in persAttr.keys(): #checking if no value is stored yet
        persAttr["highscore"] = 0
    if "lives" not in persAttr.keys():
        persAttr["lives"] = 0
    if "rank" not in persAttr.keys():
        persAttr["rank"] = rank
    if "lost" not in persAttr.keys():
        persAttr["lost"] = False
    if "gamesPlayed" not in persAttr.keys():
        persAttr["gamesPlayed"] = 0

    attr["alexaWord"] = random.choice(category_data)
    attr["used_words"] = usedWords
    attr["score"] = scoreInitial
    attr["lives"] = livesInitial
    attr["category_data"] = wordSubList
    attr["responded"] = False
    attr["lost"] = False
    attr["rank"] = persAttr["rank"]
    
    persAttr["gamesPlayed"] += 1

    #clearing db of unncessecary data
    highscoreSaved = persAttr["highscore"]
    livesSaved = persAttr["lives"]
    rankSaved = persAttr["rank"]
    gamesPlayedSaved = persAttr["gamesPlayed"]
    handler_input.attributes_manager.delete_persistent_attributes()
    persAttr = handler_input.attributes_manager.persistent_attributes
    persAttr["highscore"] = highscoreSaved
    persAttr["lives"] = livesSaved
    persAttr["rank"] = rankSaved
    persAttr["lost"] = attr["lost"]
    persAttr["gamesPlayed"] = gamesPlayedSaved
    persAttr["score"] = 0
    
    handler_input.attributes_manager.save_persistent_attributes()
    
    category_data.remove(attr["alexaWord"]) #preventing repeats
    attr["used_words"].append(attr["alexaWord"]) #preventing repeats
    
    finalSpeech = starter_text.format(persAttr["highscore"], attr["alexaWord"])

    handler_input.response_builder.speak(speech + " " + finalSpeech).ask(noTimeText)
    
    return handler_input.response_builder.response

@sb.request_handler(can_handle_func = is_intent_name("AMAZON.HelpIntent"))
def help_intent_handler(handler_input):
    attr = handler_input.attributes_manager.session_attributes
    if "alexaWord" in attr.keys():
        speech = help_text.format(attr["alexaWord"])
        handler_input.response_builder.speak(speech).ask(speech)
    else:
        speech = "If you want help, say, play a game, and then ask for help."
        handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response

@sb.request_handler(
    can_handle_func= lambda handler_input:
        is_intent_name("AMAZON.CancelIntent")(handler_input) or
        is_intent_name("AMAZON.StopIntent")(handler_input))
def cancel_and_stop_intent_handler(handler_input):
    attr = handler_input.attributes_manager.session_attributes
    speech = "Thanks for playing! Your score was {}. Play again soon!".format(attr["score"])
    handler_input.response_builder.set_should_end_session(True)
    return handler_input.response_builder.speak(speech).response

#HELPER FUNCTION FOR word_select_handler
def getNextWord(handler_input, userWord, alexaWord):
    attr = handler_input.attributes_manager.session_attributes
    if (userWord not in attr["category_data"]) and (userWord[0] == alexaWord[len(alexaWord) - 1]):
        while True:
            choice = random.choice(attr["category_data"])
            if choice[0] == userWord[len(userWord) - 1]:
               attr["category_data"].remove(choice)
               return choice
    else:
        return "0"

@sb.request_handler(can_handle_func = is_intent_name("SelectWordIntent"))
def select_word_handler(handler_input):
    attr = handler_input.attributes_manager.session_attributes
    persAttr = handler_input.attributes_manager.persistent_attributes
    userWord = handler_input.request_envelope.request.intent.slots["currWord"].value.lower()
    
    #change numbers to letter form
    nums = ["zero", "one", "two", "three","four","five","six","seven","eight","nine","ten"]
    for i in range(len(nums)):
        userWord = userWord.replace(str(i), nums[i])
    speech = ""

    #user responded
    attr["responded"] = True
    attr["lost"] = False
    
    '''
    #REMOVED BECAUSE WORDS LIKE RACECAR, STARFISH, & EGGSHELL register as multiple words
    elif len(userWord.split(" ")) > 1: #CASE FOR MORE THAN ONE WORD BEING SAID
        attr["lives"] = attr["lives"] - 1
        if attr["lives"] == 0:
            speech = ("That was more than one word, which is not allowed!")
    '''

    if(userWord in attr["used_words"]):
        attr["lives"] = attr["lives"] - 1
        if attr["lives"] == 0:
            speech = ("Oops! Looks like we've already used that word.")
    
    elif(userWord[0] == (attr["alexaWord"][len(attr["alexaWord"])-1])):    
        attr["used_words"].append(userWord)    
        foundOne = False
        for i in range(len(attr["category_data"])):
            newChoice = random.choice(attr["category_data"])
            if newChoice[0] == userWord[len(userWord) - 1].lower():
                attr["alexaWord"] = newChoice
                foundOne = True
                break
        
        #checking if alexa found a word, if not the user wins
        if not foundOne:
            speech = ("The word {} works! Hmm. I can't think of a word. You win this time. Your final score was {}. I'll award you with a free extra life for winning.").format(userWord, attr["score"])
            handler_input.response_builder.set_should_end_session(True)
        else:
            newAlexaWord = attr["alexaWord"]
            attr["used_words"].append(newAlexaWord)
            attr["score"] += scoreIncrement
            
            speech = ("The word {} works! Your score is {}. My next word is, {}").format(userWord, attr["score"], newAlexaWord)
            attr["responded"] = False
    else:
        attr["lives"] = attr["lives"] - 1
        if attr["lives"] == 0:
            attr["lost"] = True
            speech = ("That word does not work!")
    
    if attr["lives"] == 0:

        #setting new high scores
        if persAttr["highscore"] < attr["score"]:
            persAttr["highscore"] = attr["score"]
            speech += " You've reached a new high score of {}!".format(attr["score"])
        elif persAttr["highscore"] == attr["score"]:
            speech += " You've tied your high score of {}!".format(attr["score"])
        else:
            speech += " You had {} points, only {} away from your high score!".format(attr["score"], persAttr["highscore"] - attr["score"])
        
        #setting new ranks
        rankKeys = list(ranks)
        for i in range(1, len(rankKeys) - 1):
            if persAttr["highscore"] >= int(rankKeys[i - 1]) and persAttr["highscore"] < int(rankKeys[i]):
                if attr["rank"] == ranks[rankKeys[i - 1]]:
                    speech += " Your linker rank is, {}.".format(attr["rank"])
                else:
                    attr["rank"] = ranks[rankKeys[i - 1]]
                    speech += " You've achieved the new linker rank, {}.".format(attr["rank"])
        if persAttr["highscore"] >= int(rankKeys[len(rankKeys) - 1]):
            if attr["rank"] == ranks[rankKeys[len(rankKeys) - 1]]:
                    speech += " Your linker rank is, {}.".format(attr["rank"])
            else:
                attr["rank"] = ranks[rankKeys[len(rankKeys) - 1]]
                speech += " You've achieved the new linker rank, {}.".format(attr["rank"])


        productResponse = in_skill_product_response(handler_input)
        product = productResponse.in_skill_products[0]

        if persAttr["lives"] == 1:
            speech += " You have {} extra life. If you would like to use one and continue this letter link, say 'use a life'. If you want to start a new link, say 'play letter linker'. Otherwise, say 'exit game'".format(persAttr["lives"])
        elif persAttr["lives"] > 0:
            speech += " You have {} extra lives. If you would like to use one and continue this letter link, say 'use a life'. If you want to start a new link, say 'play letter linker'. Otherwise, say 'exit game'".format(persAttr["lives"])
        else:
            speech += " You have no extra lives to use. If you want some extra lives, say 'get extra lives'. If you want to play again, say 'play letter linker'. If you want to exit the game, say 'exit game'."

        handler_input.response_builder.speak(speech).ask(speech)
    else:
        handler_input.response_builder.speak(speech).ask(noTimeText)
    
    #saving attributes everytime
    persAttr["score"] = attr["score"]
    persAttr["rank"] = attr["rank"]
    persAttr["used_words"] = attr["used_words"]
    persAttr["category_data"] = attr["category_data"]
    persAttr["lost"] = attr["lost"]
    handler_input.attributes_manager.save_persistent_attributes()

    return handler_input.response_builder.response

@sb.request_handler(can_handle_func = is_intent_name("GetLivesIntent"))
def get_lives_intent_handler(handler_input):
    speech = "The Letter Linker Store offers, "
    products = in_skill_product_response(handler_input)
    for i in products.in_skill_products:
        speech += str(i.reference_name) + ". "

    speech += "To buy, say, 'buy', followed by the product name."
    speech +=  " If you'd like to play Letter Linker instead, say, play letter linker."
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response

@sb.request_handler(can_handle_func = is_intent_name("BuyIntent"))
def buy_intent_handler(handler_input):
    attr = handler_input.attributes_manager.session_attributes
    persAttr = handler_input.attributes_manager.persistent_attributes
    
    try:
        userProduct = handler_input.request_envelope.request.intent.slots["product"]
        productName = userProduct.value.lower().replace(" ","")
    except:
        productName = ""

    products = in_skill_product_response(handler_input)
    product = None
    persAttr["livesToAdd"] = 0
    if "10" in productName:
        product = products.in_skill_products[2]
        persAttr["livesToAdd"] = 10
    elif "20" in productName:
        product = products.in_skill_products[1]
        persAttr["livesToAdd"] = 20
    elif "single" in productName or "one" in productName or "extralife" in productName:
        product = products.in_skill_products[0]
        persAttr["livesToAdd"] = 1
    else:
        product = products.in_skill_products[0]
        persAttr["livesToAdd"] = 1

    handler_input.attributes_manager.save_persistent_attributes()
    return handler_input.response_builder.add_directive(
        SendRequestDirective(
            name="Buy",
            payload={
                "InSkillProduct": {
                    "productId": product.product_id
                }
            },
            token="correlationToken")
    ).response

@sb.request_handler(can_handle_func = is_intent_name("RefundIntent"))
def refund_intent_handler(handler_input):
    attr = handler_input.attributes_manager.session_attributes
    persAttr = handler_input.attributes_manager.persistent_attributes
    
    try:
        userProduct = handler_input.request_envelope.request.intent.slots["product"]
        productName = userProduct.value.lower().replace(" ","")
    except:
        productName = ""

    products = in_skill_product_response(handler_input)
    product = None
    persAttr["livesToAdd"] = 0
    if "10" in productName:
        product = products.in_skill_products[2]
        persAttr["livesToAdd"] = -10
    elif "20" in productName:
        product = products.in_skill_products[1]
        persAttr["livesToAdd"] = -20
    elif "single" in productName or "one" in productName or "extralife" in productName:
        product = products.in_skill_products[0]
        persAttr["livesToAdd"] = -1
    
    handler_input.attributes_manager.save_persistent_attributes()
    return handler_input.response_builder.add_directive(
        SendRequestDirective(
            name="Cancel",
            payload={
                "InSkillProduct": {
                    "productId": product.product_id
                }
            },
            token="correlationToken")
    ).response

@sb.request_handler(can_handle_func = is_intent_name("UseLifeIntent"))
def use_life_intent_handler(handler_input):
    attr = handler_input.attributes_manager.session_attributes
    persAttr = handler_input.attributes_manager.persistent_attributes

    if persAttr["lives"] > 0:
        persAttr["lives"] -= 1
        attr["lives"] = 1
        
        handler_input.attributes_manager.save_persistent_attributes()   

        #calling helper
        return continuedGame(handler_input)    
    else:
        speech = " You have no extra lives to use. If you want some extra lives, say 'get extra lives'. If you want to play again, say 'play letter linker'. If you want to exit the game, say 'exit game'."
        handler_input.response_builder.speak(speech).ask(speech)
        return handler_input.response_builder.response
    
@sb.request_handler(can_handle_func=lambda handler_input: is_request_type("Connections.Response")(handler_input) and (handler_input.request_envelope.request.name == "Buy" or handler_input.request_envelope.request.name == "Cancel"))
def buy_response_handler(handler_input):
    attr = handler_input.attributes_manager.session_attributes
    persAttr = handler_input.attributes_manager.persistent_attributes

    #connection went through
    if handler_input.request_envelope.request.status.code == "200":
        speech = ""
        reprompt = ""
        purchaseResult = handler_input.request_envelope.request.payload.get("purchaseResult")
        
        if purchaseResult == PurchaseResult.ACCEPTED.value:
            if persAttr["lives"] + persAttr["livesToAdd"] >= 0:
                persAttr["lives"] += persAttr["livesToAdd"] #set back to one cuz you need to include A USE A WORD REQUEST TO USER HERE
            persAttr["livesToAdd"] = 0
            
            #plural grammar
            if persAttr["lives"] == 1:
                speech += " You now have {} extra life.".format(persAttr["lives"])
            else:
                speech += " You now have {} extra lives.".format(persAttr["lives"])

            if persAttr["lost"]:

                #maintaining previous game
                attr["used_words"] = persAttr["used_words"]
                attr["score"] = persAttr["score"]
                persAttr["lost"] = False
                
                speech += " If you would like to use one and continue this letter link, say 'use a life'. If you'd like to play a new game, say 'play letter linker'. If not, say 'exit game'."
                handler_input.response_builder.speak(speech).ask(speech)
                handler_input.attributes_manager.save_persistent_attributes()   
                return handler_input.response_builder.response
            else:
                speech += " If you would like to play a game, say 'play letter linker'. If not, say 'exit game'."
                handler_input.response_builder.speak(speech).ask(speech)
                handler_input.attributes_manager.save_persistent_attributes()   
                return handler_input.response_builder.response

        elif purchaseResult in (
                    PurchaseResult.DECLINED.value,
                    PurchaseResult.ERROR.value,
                    PurchaseResult.NOT_ENTITLED.value):
            speech = "If you'd like to play a new game, say 'play letter linker'. If you'd like to exit the game, say 'exit game'."
            handler_input.response_builder.speak(speech).ask(speech)
            return handler_input.response_builder.response

@sb.request_handler(can_handle_func=is_request_type("SessionEndedRequest"))
def session_ended_request_handler(handler_input):
    attr = handler_input.attributes_manager.session_attributes
    persAttr = handler_input.attributes_manager.persistent_attributes
    
    if ("score" in persAttr.keys()):
        attr["score"] = persAttr["score"]    
    
    if persAttr["highscore"] < attr["score"]:
        persAttr["highscore"] = attr["score"]
    
    handler_input.attributes_manager.save_persistent_attributes()
    return handler_input.response_builder.response

@sb.request_handler(can_handle_func = is_intent_name("PlayAgainIntent"))
def play_again_intent_handler(handler_input):
    return launch_request_handler(handler_input)

'''Deleted for intent space
@sb.request_handler(can_handle_func = is_intent_name("RepeatWordIntent"))
def repeat_word_intent_handler(handler_input):
    attr = handler_input.attributes_manager.session_attributes
    speech = ("My word is, {}.".format(attr["alexaWord"]))
    
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response
'''

@sb.request_handler(can_handle_func = is_intent_name("ScoreInquiryIntent"))
def score_inquiry_intent_handler(handler_input):
    attr = handler_input.attributes_manager.session_attributes
    speech = ("Your score is currently {}.".format((attr["score"])))
    
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response

@sb.request_handler(can_handle_func = is_intent_name("LifeInquiryIntent"))
def life_inquiry_intent_handler(handler_input):
    persAttr = handler_input.attributes_manager.persistent_attributes
    
    if persAttr["lives"] == 1:
        speech = ("You have {} extra life.".format((persAttr["lives"])))
    elif persAttr["lives"] >= 0:
        speech = ("You have {} extra lives.".format((persAttr["lives"])))
    
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response

'''Deleted for intent space
@sb.request_handler(can_handle_func = is_intent_name("HighScoreInquiryIntent"))
def high_score_inquiry_intent_handler(handler_input):
    attr = handler_input.attributes_manager.session_attributes
    persAttr = handler_input.attributes_manager.persistent_attributes
    speech = ("Your high score is {}.".format((persAttr["highscore"])))
    
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response
'''

@sb.request_handler(can_handle_func = is_intent_name("LetterInquiryIntent"))
def letter_inquiry_intent_handler(handler_input):
    attr = handler_input.attributes_manager.session_attributes
    speech = ("My word is, {}. So your next word must start with the letter {}.".format(attr["alexaWord"],(attr["alexaWord"][len(attr["alexaWord"])-1])))
    handler_input.response_builder.speak(speech).ask(noTimeText)
    return handler_input.response_builder.response

@sb.request_handler(can_handle_func = is_intent_name("EndGameIntent"))
def end_game_intent_handler(handler_input):
    return endGame(handler_input)

@sb.request_handler(can_handle_func=is_intent_name("AMAZON.FallbackIntent"))
def fallback_handler(handler_input):
    attr = handler_input.attributes_manager.session_attributes
    speech = (
        "Make sure that you're saying, my word is, followed by your word. Once again my word is, {}." 
        ).format(attr["alexaWord"])
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response

@sb.request_handler(can_handle_func = lambda input: True)
def unhandled_intent_handler(handler_input):
    speech = "Hm. I'm not sure what to do there. Say a word that links to mine!!" #mayb edit to fit game better 
    
    attr = handler_input.attributes_manager.session_attributes
    persAttr = handler_input.attributes_manager.persistent_attributes
    
    if attr["responded"] == False:
        speech = ""
        speech += "You didn't answer in time!"
        if persAttr["highscore"] < attr["score"]:
            persAttr["highscore"] = attr["score"]
            speech += " You've reached a new high score of {}!".format(attr["score"])
        elif persAttr["highscore"] == attr["score"]:
            speech += " You've tied your high score of {}!".format(attr["score"])
        else:
            speech += " You had {} points, only {} away from your high score!".format(attr["score"], persAttr["highscore"] - attr["score"])
        
        speech += " Thanks for playing!"
            
        handler_input.attributes_manager.save_persistent_attributes()   
        handler_input.response_builder.set_should_end_session(True)
    
    
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response

@sb.global_response_interceptor()
def log_response(handler_input, response):
    """Log response from alexa service."""
    logger.info("Response: {}".format(response))

"""@sb.global_request_interceptor()
def log_request(handler_input):
    #Log request to alexa service.
    print("Alexa Request: {}\n".format(handler_input.request_envelope.request))"""

@sb.exception_handler(can_handle_func=lambda i, e: True)
def all_exception_handler(handler_input, exception):
    """Catch all exception handler, log exception and
    respond with custom message.
    """
    speech = "Sorry, something went wrong. Please relaunch the skill!"
    
    handler_input.response_builder.speak(speech).ask(speech)
    handler_input.response_builder.set_should_end_session(True)
    return handler_input.response_builder.response

lambda_handler = sb.lambda_handler()
