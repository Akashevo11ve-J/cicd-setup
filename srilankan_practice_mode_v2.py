'''This version is for practice session across all the grades for three subjects. The chapter has been used as metafilter for each subject'''

import base64 
import imghdr
from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Union, Any
import os
import pandas as pd
from pinecone import Pinecone
import openai
from openai import AsyncOpenAI
import logging
from logging.handlers import RotatingFileHandler
from collections import defaultdict
import threading
import json
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv
from anthropic import AsyncAnthropic
import re
from google import genai
import vertexai
from vertexai.generative_models import (
    GenerativeModel,
    Part,
    HarmCategory,
    HarmBlockThreshold,
    Tool
)
from vertexai.generative_models import (
    Content
)
from vertexai.generative_models import (
    FunctionDeclaration
)
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import asyncio


load_dotenv()
# Set up Claude API Key
# Claude client
claude_client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
API_KEY = os.getenv("GEMINI_API_KEY")
genai_client = genai.Client(api_key=API_KEY)

DBExecutor = ThreadPoolExecutor(max_workers=4)
AIExecutor = ThreadPoolExecutor(max_workers=4)

#Setup rotating file handler for logging
log_file_handler = RotatingFileHandler('practice_app_logs.log', maxBytes=10000000, backupCount=5, encoding='utf8')
log_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - PID:%(process)d - Thread:%(threadName)s - %(message)s'))
logger = logging.getLogger()
logger.addHandler(log_file_handler)
logger.setLevel(logging.INFO)


mongo_url = os.getenv("MONGO_DB_URI")
client = MongoClient(mongo_url)
# client = MongoClient("mongodb://localhost:27017")
db = client["db"]
collection = db["practice_session"]
collection_practicehistory = db["practice_history"]

openai.api_key = os.environ["OPENAI_API_KEY"]
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

#client = OpenAI(api_key=KEY)
# Load RAG Index
pc_api_key = os.environ.get("PINECONE_API_KEY")

# Initialize Pinecone
pc = Pinecone(api_key=pc_api_key)
#pc = Pinecone(api_key="pcsk_2QFSvn_PaPvwcny3N6TaR4NBbBXESScoKWiMm2VtWqJDdhDdVtWURkRGpQPJHUXegbKzuo")

vertexai.init(project="ivory-streamer-473110-e4", location="us-central1")  # update region
model = GenerativeModel('gemini-2.5-flash') 
client_gemini = genai.Client(
vertexai=True,
project="ivory-streamer-473110-e4",   # your GCP project ID
location="us-central1"                # region where Gemini 2.5 Pro is available
)

    # Define the model
model_id = "gemini-2.5-flash"

BOARD_INDEX_MAP = {
    "CBSE": os.getenv("EXPLORE_MODE_PCINDEX"),
    "PREP": os.getenv("EXPLORE_MODE_PCINDEX"),
    #"PREP": os.getenv("PRACTICE_MODE_PCINDEX"),#removing to accomodate additional subjects
    "SSC-BSET": os.environ.get("SSC_BSET")
}
BOARD_INDEX_MAP_NEW = {
    "CBSE": os.getenv("EXPLORE_MODE_PCINDEX"),
#    "CBSE": os.getenv("PRACTICE_MODE_PCINDEX"),
    "PREP": os.getenv("PRACTICE_MODE_PCINDEX"),
    "SSC-BSET": os.environ.get("SSC_BSET")
}

# async def get_embedding(text, model="text-embedding-ada-002"):
#     loop = asyncio.get_event_loop()
#     """Generate embeddings for a given text using a specified model."""
#     return await loop.run_in_executor(AIExecutor, openai.embeddings.create(input=[text], model=model).data[0].embedding)

async def get_embedding(text, model="text-embedding-ada-002"):
    response = openai.embeddings.create(
        input=[text],
        model=model
    )
    return response.data[0].embedding


def build_filters(subject, grade):
    """
    Builds the lower and higher grade filters based on the provided grade.
    
    Parameters:
    - subject: The subject domain for the query (e.g., 'biology').
    - grade: The grade level for the query (e.g., '10').
    
    Returns:
    A tuple of dictionaries representing the lower grade filter and the higher grade filter.
    """
    grade = float(grade)
    
    # Lower grade filter construction
    if grade == 6:
        lower_grade_filter = {
            "subject": {"$eq": subject.lower()},
            "grade": {"$eq": 6.0}
        }
    else:
        lower_grade_filter = {
            "subject": {"$eq": subject.lower()},
            "grade": {"$lte": grade, "$gte": 6.0}
        }
    
    # Higher grade filter construction
    if grade >= 12:
        higher_grade_filter = None  # No higher grades to search
    else:
        higher_grade_filter = {
            "subject": {"$eq": subject.lower()},
            "grade": {"$gt": grade, "$lte": 12.0}  # Excludes the current grade by using $gt
        }
    
    return lower_grade_filter, higher_grade_filter


# async def query_vdb(query, subject, grade, chapter,board, embed_model='text-embedding-ada-002', top_k=7):
#     """
#     Queries a vector database for text using subject-, grade-, and chapter-specific indices.

#     Parameters:
#     - query: The query string.
#     - subject: The subject domain for the query (e.g., 'biology').
#     - grade: The grade level for the query (e.g., 6.0).
#     - chapter: The chapter number to query (e.g., 1.0).
#     - embed_model: The embedding model to use for generating embeddings.
#     - top_k: The number of top matches to retrieve.
    
#     Returns:
#     A dictionary with 'contexts' containing up to top_k matches, or None if no matches are found.
#     """
#     # Generate an embedding of the query using the specified model.
#     embedding = await get_embedding(query, model=embed_model)

#     # Define the index name
#     index_name = BOARD_INDEX_MAP.get(board.upper())
#     #index_name = os.getenv("PRACTICE_MODE_PCINDEX")
    
#     # Create the metadata filter
#     metadata_filter = {
#         "subject": {"$eq": subject.lower()},
#         "grade": {"$eq": float(grade)},
#         "chapter": {"$eq": float(chapter)}
#     }
#     loop = asyncio.get_event_loop()
#     # Query the text index with metadata filter
#     text_index = pc.Index(index_name)
#     text_res = await loop.run_in_executor(DBExecutor,text_index.query(
#         vector=embedding,
#         filter=metadata_filter,
#         top_k=top_k,
#         include_metadata=True
#     ))

#     # Process the results
#     contexts = [{
#         'text': match['metadata']['text'],
#         'Grade': match['metadata']['grade'],
#         'Subject': match['metadata']['subject'],
#         'Chapter': match['metadata']['chapter']
#     } for match in text_res['matches']]
    
#     return {
#         'contexts': contexts if contexts else None
#     }




async def query_vdb(query, subject, grade, chapter, board, type,
                    embed_model='text-embedding-3-small', top_k=7):

    embedding = await get_embedding(query, model=embed_model)
    if(type=="New"):
        index_name = BOARD_INDEX_MAP_NEW.get(board.upper())
    else:
        index_name = BOARD_INDEX_MAP.get(board.upper())
    
    if (board == "SSC-BSET") or (board == "CBSE"):
        metadata_filter = {
        "subject": {"$eq": subject.title()},
        "grade": {"$eq": float(grade)},
        "chapter": {"$eq": float(chapter)},
        "type":{"$eq":type}
    }
    else :
        metadata_filter = {
        "subject": {"$eq": subject.lower()},
        "grade": {"$eq": float(grade)},
        "chapter": {"$eq": float(chapter)}
    }
    text_index = pc.Index(index_name)
    text_res = text_index.query(
        vector=embedding,
        filter=metadata_filter,
        top_k=top_k,
        include_metadata=True
    )
    contexts = [{
        'text': match['metadata']['text'],
        'Grade': match['metadata']['grade'],
        'Subject': match['metadata']['subject'],
        'Chapter': match['metadata']['chapter']
    } for match in text_res['matches']]

    return {'contexts': contexts or None}



async def query_vdb_nec(query, subject, grade, embed_model='text-embedding-ada-002', top_k=7):
    """
    Queries a vector database for text and related images using subject- and grade-specific filters.
    
    Parameters:
    - query: The query string.
    - subject: The subject domain for the query (e.g., 'biology').
    - grade: The grade level for the query (e.g., '10').
    - embed_model: The embedding model to use for generating embeddings.
    - top_k: The number of top matches to retrieve.
    
    Returns:
    A dictionary with 'lower_grade_contexts', 'higher_grade_contexts', and 'images' 
    where each contains up to top_k matches, or None if no matches are found.
    """
    # Generate an embedding of the query using the specified model.
    embedding = await get_embedding(query, model=embed_model)

    # Define the index name
    index_name = "srilankanec"

    async def query_index(metadata_filter):
        index = pc.Index(index_name)
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(DBExecutor,index.query(vector=embedding, filter=metadata_filter, top_k=top_k, include_metadata=True))
        filtered_matches = list(filter(lambda match: match['score'] > 0.75, res['matches']))
        
        return [{
            'text': match['metadata'].get('text', ''),
            'grade': match['metadata'].get('grade', ''),
            'subject': match['metadata'].get('subject', '')
        } for match in filtered_matches]

    # Build lower and higher grade filters using the helper function
    lower_grade_filter, higher_grade_filter = build_filters(subject, grade)

    # Define image filter
    image_filter = {
        "subject": {"$eq": "biology image"}
    }

    # Query indices in parallel
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_filter = {
            executor.submit(query_index, lower_grade_filter): 'lower_grade_contexts',
            executor.submit(query_index, higher_grade_filter): 'higher_grade_contexts',
            executor.submit(query_index, image_filter): 'images'
        }
        
        results = {}
        for future in concurrent.futures.as_completed(future_to_filter):
            filter_name = future_to_filter[future]
            try:
                results[filter_name] = future.result()
            except Exception as exc:
                logger.error(f'{filter_name} generated an exception: {exc}')
                results[filter_name] = None
        logger.info(f"VDB query results completed for {subject}, grade {grade}")
    return {
        'lower_grade_contexts': results['lower_grade_contexts'] if results['lower_grade_contexts'] else None,
        'higher_grade_contexts': results['higher_grade_contexts'] if results['higher_grade_contexts'] else None,
        'images': results['images'] if results['images'] else None
    }


def format_results(current_context):
    contexts = current_context.get('contexts', [])

    # Format the results
    result = "Context for the query is:\n\n"
    
    if not contexts:
        result += "There is no context available."
    else:
        for context in contexts:
            result += f"{context['text']}\n\n"

    return result


last_valid_context = ""

async def transcribe_image_to_text(image_data):
    image_format = imghdr.what(None, h=image_data)
    if image_format not in ['jpeg', 'png']:
        raise HTTPException(status_code=400, detail="Unsupported image format. Only JPEG and PNG are allowed.")

    base64_image = base64.b64encode(image_data).decode('utf-8')
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe everything you see in this image. Include objects, text, diagrams, and any details. If there's handwritten or printed text, transcribe it exactly"},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/{image_format};base64,{base64_image}"}}
                    ],
                }
            ],
            max_tokens=300
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error during image transcription: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    

def get_key_ideas(chapter, subject, grade, board, type):
    print(f"type in get key ideas: {type}  ")
    # Load appropriate CSV based on board
    
    if board == "CBSE" or board == "PREP":
        df = pd.read_csv(f"/home/ubuntu/main_apis/{type}_combined_key_topics.csv")
    elif board == "SSC-BSET":
        df = pd.read_csv(f"/home/ubuntu/main_apis/bset_key_topics.csv")
    elif board == "IGCSE":
        df = pd.read_csv(f"/home/ubuntu/main_apis/igcse_key_topics.csv")
    else:  # NEC
        df = pd.read_csv(f"/home/ubuntu/main_apis/nec_key_topics.csv")
    
    #Convert inputs to lowercase and to string
    

    # if board == "CBSE" or board == "PREP":
    #     print(f"{type}_combined_key_topics.csv")
    #     df = pd.read_csv(f"./{type}_combined_key_topics.csv")
    # elif board == "SSC-BSET":
    #     df = pd.read_csv('./bset_key_topics.csv')  
    # elif board == "IGCSE":
    #     df = pd.read_csv('./igcse_key_topics.csv')
    # else:  # NEC
    #     df = pd.read_csv('./nec_key_topics.csv')
    #Convert inputs to lowercase and to string
    subject = str(subject).lower()
    grade = str(grade)
    chapter = str(chapter)
    
    # Filter the dataframe
    filtered_df = df[
        (df['chapter_no'].astype(str) == chapter) & 
        (df['subject'].str.lower() == subject) & 
        (df['grade'].astype(str) == grade)
    ]
    
    return filtered_df['key_ideas'].tolist()

# Add board parameter to get_chapter_name
def get_chapter_name(chapter, subject, grade, board, type):
    # Load appropriate CSV based on board
    if board == "CBSE" or board == "PREP":
        df = pd.read_csv(f"/home/ubuntu/main_apis/{type}_combined_key_topics.csv")
    elif board == "SSC-BSET":
        df = pd.read_csv(f"/home/ubuntu/main_apis/bset_key_topics.csv")
    elif board == "IGCSE":
        df = pd.read_csv(f"/home/ubuntu/main_apis/igcse_key_topics.csv")
    else:  # NEC
        df = pd.read_csv(f"/home/ubuntu/main_apis/nec_key_topics.csv")
    
    # if board == "CBSE":
    #     df = pd.read_csv(f"./{type}_combined_key_topics.csv")
    # elif board == "SSC-BSET":
    #     df = pd.read_csv('./bset_key_topics.csv')
    # elif board == "IGCSE":
    #     df = pd.read_csv('./igcse_key_topics.csv')
    # else:  # NEC
    #     df = pd.read_csv('./nec_key_topics.csv')
    # Convert inputs to lowercase and to string
    subject = str(subject).lower()
    grade = str(grade)
    chapter = str(chapter)
    
    # Filter the dataframe
    filtered_df = df[
        (df['chapter_no'].astype(str) == chapter) & 
        (df['subject'].str.lower() == subject) & 
        (df['grade'].astype(str) == grade)
    ]
    
    return filtered_df['chapter_name'].iloc[0] if not filtered_df.empty else None

async def query_transformation(query, conversation_history):

    # Prepare the full query with conversation history
    history_text = "\n".join(f"{exchange['role'].title()}: {exchange['content']}" for exchange in conversation_history)



    full_query = f"""

    ###Instruction###


        You are a helpful assistant who rewrites the students query during an assessment session.

        There can be two kinds of scenarios.

        One is when student is choosing a topic - They can be very brief and indirect.
        They may answer like A or 1.

        You have to look in history and rewrite it as what they are asking.

        Second scenario is when they are answering a question 

        You combine the users response and associated question asked together.

        You must seprate it out in below format

        Question: Last Question Asked - For MCQ, Match the following - Put the complete question with their options or columns.
        Students Response: Students Response as it is.

        Sometimes student keep on answering a question wrong again again - Make sure to keep track and generate question and associated answer each time - till the question has been changed.
        Look into conversation history.


        Dont correct their responses in MCQs, Fill in the blanks, true or False, Match the following etc

        In history - we have User tag for students query.

        When conversation history is empty - Let it be the students query alone.

        ###Conversation History###
        {history_text}

        ###User Query###
        {query}

        ### Answer Style ###
        Do not write anything else. Just produce the transformed query or original query as you think. It will go into vector database. So make sure you must not write anything else. 
        """

    # Sending the query to OpenAI
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": full_query,
                },
            ],
        )

        # Extracting the response
        response = completion.choices[0].message.content
        return response
    except Exception as e:
        logger.error(f"Error in processing query in query transformation: {e}")
        return "An error occurred while processing the query."


async def change_of_topic(query, conversation_history):

    # Prepare the full query with conversation history
    history_text = "\n".join(f"{exchange['role'].title()}: {exchange['content']}" for exchange in conversation_history)

    full_query = f"""

        ###Instruction###

        You are a helpful assistant who judges whether the student is choosing a topic when suggested by assistant or requesting the change of the topic or suggesting a topic.
    
        You reply in yes or no. You dont write anything else. \n
     


        You have to judge from the history of the conversation. The conversation history will be an interaction betwee user and assistant. Assistant is trying to put some topics intially 
        to initiate the practice session. Student is to choose a topic. Then a question is generated by assistant. This is the initial phase of the conversation. 

        Student can answer the question, or suggest to ask the questions from some other topic. Judge Carefully. 

        ###Conversation History###
        {history_text}

        ###User Query###
        {query}

        ### Answer Style ###
        Do not write anything else. Just say yes or no. Make sure you must not write anything else. 

        """

    # Sending the query to OpenAI
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": full_query,
                },
            ],
        )

        # Extracting the response
        response = completion.choices[0].message.content
        return response
    except Exception as e:
        logger.error(f"Error in processing query in change of topic: {e}")
        return "An error occurred while processing the query."

class SessionContextManager:
    def __init__(self):
        self.contexts = defaultdict(lambda: {"current": "", "last_valid": ""})
        self.lock = threading.Lock()

    def get_context(self, session_id):
        with self.lock:
            return self.contexts[session_id]["current"] or self.contexts[session_id]["last_valid"]

    def set_context(self, session_id, context):
        with self.lock:
            self.contexts[session_id]["current"] = context
            if context:  # If we have a new valid context, update last_valid
                self.contexts[session_id]["last_valid"] = context

    def clear_context(self, session_id):
        with self.lock:
            if session_id in self.contexts:
                del self.contexts[session_id]


session_context_manager = SessionContextManager()

def get_cached_subject_content(subject, grade, chapter, board, type):
    if board == "CBSE":
        cache_file_paths = {
            "math": f"/home/ubuntu/experiments/scrapingquestions/{type}/Maths/Class{grade}/chapter{chapter}.md",
            "chemistry": f"/home/ubuntu/experiments/scrapingquestions/{type}/Chemistry/Class{grade}/chapter{chapter}.md",
            "physics": f"/home/ubuntu/experiments/scrapingquestions/{type}/Physics/Class{grade}/chapter{chapter}.md",       
        }
    elif board == "PREP":
        cache_file_paths = {
            "math": f"/home/ubuntu/experiments/scrapingquestionsPREP/{type}/Maths/Class{grade}/chapter{chapter}.md",
            "chemistry": f"/home/ubuntu/experiments/scrapingquestionsPREP/{type}/Chemistry/Class{grade}/chapter{chapter}.md",
            "physics": f"/home/ubuntu/experiments/scrapingquestionsPREP/{type}/Physics/Class{grade}/chapter{chapter}.md",       
        }
    elif board == "SSC-BSET":
        cache_file_paths = {
            "math": f"/home/ubuntu/experiments/scrapingquestionsBSET/Maths/Class{grade}/chapter{chapter}.md",
            "chemistry": f"/home/ubuntu/experiments/scrapingquestionsBSET/Chemistry/Class{grade}/chapter{chapter}.md",
            "physics": f"/home/ubuntu/experiments/scrapingquestionsBSET/Physics/Class{grade}/chapter{chapter}.md",       
        }
    elif board == "IGCSE":
        cache_file_paths = {
            "math": f"/home/ubuntu/experiments/scrapingquestionsIGCSE/Maths/Class{grade}/chapter{chapter}.md",
            "chemistry": f"/home/ubuntu/experiments/scrapingquestionsIGCSE/Chemistry/Class{grade}/chapter{chapter}.md",
            "physics": f"/home/ubuntu/experiments/scrapingquestionsIGCSE/Physics/Class{grade}/chapter{chapter}.md",       
        }
    #/home/ubuntu/experiments/scrapingquestionsBSET/Chemistry/Class6
    else:  # NEC
        if subject != "math":
            raise ValueError("No support")
        cache_file_paths = {
            "math": f"/home/ubuntu/experiments/scrapingquestions/NEC/Maths/Class {grade}/Chapter{chapter}_scraped_questions.md",
           
        }

#     if board == "CBSE" or board == "PREP":
#         cache_file_paths = {
#         "math": f"C:\\Users\\vaish\\evo11ve\\code_1804\\AI-Scripts-on-Server\\scraping_questions\\{type}\\Maths\\Class {grade}\\chapter{chapter}.md",
#         "chemistry": f"C:\\Users\\vaish\\evo11ve\\code_1804\\AI-Scripts-on-Server\\scraping_questions\\{type}\\Chemistry\\Class {grade}\\chapter{chapter}.md",
#         "physics": f"C:\\Users\\vaish\\evo11ve\\code_1804\\AI-Scripts-on-Server\\scraping_questions\\{type}\\Physics\\Class {grade}\\chapter{chapter}.md",
        
#     }
#     elif board == "SSC-BSET":
#         cache_file_paths = {
#             "math": f"C:\\Users\\vaish\\evo11ve\\code_1804\\AI-Scripts-on-Server\\scraping_questions_BSET\\Maths\\Class{grade}\\chapter{chapter}.md",
#             "chemistry": f"C:\\Users\\vaish\\evo11ve\\code_1804\\AI-Scripts-on-Server\\scraping_questions_BSET\\Chemistry\\Class{grade}\\chapter{chapter}.md",
#             "physics": f"C:\\Users\\vaish\\evo11ve\\code_1804\\AI-Scripts-on-Server\\scraping_questions_BSET\\Physics\\Class{grade}\\chapter{chapter}.md",       
#         }
#     elif board == "IGCSE":
#         cache_file_paths = {
#             "math": f"C:\\Users\\vaish\\evo11ve\\code_1804\\AI-Scripts-on-Server\\scrapingquestionsIGCSE\\Maths\\Class{grade}\\chapter{chapter}.md",
#             "chemistry": f"C:\\Users\\vaish\\evo11ve\\code_1804\\AI-Scripts-on-Server\\scrapingquestionsIGCSE\\Chemistry\\Class{grade}\\chapter{chapter}.md",
#             "physics": f"C:\\Users\\vaish\\evo11ve\\code_1804\\AI-Scripts-on-Server\\scrapingquestionsIGCSE\\Physics\\Class{grade}\\chapter{chapter}.md",       
#         }
#     else:  # NEC
#         if subject != "math":
#             raise ValueError("No support")
#         cache_file_paths = {
#         "math": f"D:\\AI-Scripts-on-Server\\scraping questions\\Maths\\Class {grade}\chapter{chapter}.md"
    
# }

    cache_file = cache_file_paths.get(subject)
    if not cache_file:
        raise ValueError(f"Invalid subject: {subject}")
    
    if not os.path.exists(cache_file):
        raise FileNotFoundError(f"Cache file not found: {cache_file}")
    
    with open(cache_file, 'r',encoding="utf-8") as file:
        return file.read()


async def process_subject_query(name, query, grade, conversation_history, subject, chapter, board, type, image_data=None):
    history_text = "\n".join(f"{exchange['role'].title()}: {exchange['content']}" for exchange in conversation_history)
   
    cached_content = get_cached_subject_content(subject, grade, chapter, board, type)
    key_ideas = get_key_ideas(chapter, subject, grade, board, type)
    chapter_name = get_chapter_name(chapter, subject, grade, board, type)

    #board_display = "Telangana State Board " if board == "SSC-BSET" else "CBSE"
    if (board == "SSC-BSET"):
        board_display = "Telangana State Board "
    elif(board=="IGCSE"):
        board_display = "IGCSE Cambridge"
    else: 
        board_display = "CBSE"
    identity_curriculum = f"You are an AI-powered teacher specializing in practice session for {board_display} Curriculum for "
    identity_prep = f"You are an AI-powered teacher specializing in practice session for JEE, NEET and competitive examinations for "
    question_levels_curriculum = f"""Question level : Remember, Understand, Apply - You must start from remember level questions and Keep on increasing the level till Apply when student correctly attemps a coginitive level.
    Sometimes you generate apply level questions and simply name them as Remember or Understand level. Dont do that.
    Ask atleast three questions in a cognitive level before moving to next level. Dont ask Analyze and Evaluate level questions in CBSE Curriculum practice session.  """
    question_levels_prep = f"""Question level : Apply, Analyze, Evaluate - You must start from Apply level questions and Keep on increasing the level when student correctly attemps a coginitive level. Ask atleast three questions in a
    cognitive level before moving to next level."""  

    if(board=="PREP"):
        question_level = question_levels_prep
        identity = identity_prep
    else:
        question_level = question_levels_curriculum
        identity = identity_curriculum

    # if board == "NEC":
    #     language_instruction = """
    #     Preserve all technical terms with Sinhala equivalents in parentheses where applicable
    #     You must must produce your reponse in spoken Sinhalese using Sinhalese Script. Use English words for proper nouns, technical terms, places, equations etc.

    #     When you give the list of topics - Give in English too. 


    #     Translation requirements:

    #     Maintain academic tone appropriate for students

    #     Preserve all technical terms with Sinhala equivalents in parentheses where applicable

    #     Keep any mathematical formulas, chemical symbols, or scientific notation unchanged

    #     For cultural references, provide appropriate local context if needed
    #     """
    # else:
    language_instruction = """
        You must produce your response in English.
        
        Use clear, simple English appropriate for students.
        Keep all technical terms, formulas, and scientific notation in standard English format.
        """

    full_query = f"""{language_instruction}

    Give me a JSON dict. Do not write anything else.

    NEVER REPEAT QUESTIONS IN A PRACTICE SESSION. YOU CAN WATCH IN CONVERSATION HISTORY TO KEEP TRACK.

    Do not use textbook word in your responses. Instead use curriculum word in your responses. 

    Never ever  ask questions which ask student to draw something as a response. Even if student asks.

CRITICAL: For matching questions, match_column_a and match_column_b MUST have the same number of items. Never create 2 items in Column A with 4 items in Column B.

When generating matching questions, ensure that the options in match_column_a and match_column_b are shuffled.

Example: below column a and b are perfectly matched. This is incorrect. Since student has to attempt it - we should not keep them perfectly matched.

match_column_a: ["1. Breathe through skin", "2. Have gills", "3. Lay eggs", "4. Photosynthesize"]
match_column_b: ["a. Fish", "b. Bird", "c. Plant", "d. Earthworm"]

    
for MCQs, write clearly question_type where it is MCQ - Single or  MCQ - Multiple

## Practice Flow

### You must not repeat question in a session. Sometimes you change the presentation of a question and repeat. Do not do that at all. 

### Number of Questions at a time
Always ask one question at a time. Do not combine multiple questions at once.

### Topic Exhaustion
Let student know a topic is exhausted when student is not able to answer Remember or Understand or Apply level questions. Let them choose another topic.

Also, a topic is exhausted when you have asked question across all cognitive domains for a topic. Do not repeat the questions. Let student know that a topic is exhausted and they have to choose another one from the list.


## Identity
{identity}  Grade {grade} subject {subject}. 

### Answer Format which will be consumed by other application
Provide your response in the following JSON format:


    You also support LaTeX equations used for academic and technical writing. Your task is to help users write LaTeX equations by providing the appropriate code. YOU MUST MUST DO IT correctly. 

    1. Inline equations: Use single dollar signs ($) to enclose inline equations. These are equations that appear within a line of text.
  

    2. Displayed equations: Use double dollar signs ($$) to enclose displayed equations. These are equations that should appear on their own line, centered.

    3. For fill in the blanks -  you must write like this - \\_\\_\\_ - with in latex equations.

   
class PracticeQuestions(BaseModel):
    "feedback": string, - Dont write question in feedback. Feedback is for feedback to answer from student and a guiding sentence for next question. Also provide the correct response - when student is unable to answer in second attempt after giving hints. After students two incorrect attempts, Include correct answer too when you are changing the question.
    "question": string, - You must Use this for question alone.
    "correct_answer": string,
    "question_type": string,
    "question_level": string,
    "mcq_options": list, Dont use word "Option", just put whatever is there.
    "match_column_a": list, Dont use word "Option", just put whatever is there. Number them as 1. 2. 3. 4. 
    "match_column_b": list, Dont use word "Option", just put whatever is there. Number them as a. b. c. d. Keep a variety in options. Sometimes you repeat.
    "attempts": int,
    "topic_chosen": string
    "percentage": int - you can give the percentage of the progress in the topic_chosen against the overall progress of the topic. This will be 100 when you have asked question across all cognitive domains for a topic
    "remarks": string - You can use this to summarize the student's strengths and weakness based on their answers in kind words. If student needs improvement in any specific areas in the topic you can mention it here. Maintain a positive tone. Encourage the student to keep trying and learning.

    "feedback": "Great choice! Let's dive into the topic of 'Deficiency Diseases'. \n Here's your first question.",
    "question": "Fill in the blank. ______________ is caused by deficiency of Vitamin D.",
    "correct_answer": "Rickets",
    "question_type": "Fill in the blanks",
    "question_level": "Remember",
    "mcq_options": [],
    "match_column_a": [],
    "match_column_b": [],
    "attempts": 0,
    "topic_chosen": "Deficiency Diseases"
    "percentage": 0
    "remarks" : "We are starting with 'Deficiency Diseases'.""

### Specific purpose of a key in answer format

1. Use the "feedback" key for the following purposes:
    - Asking a student to choose a key idea from the list of key ideas. Number them and break line.
    - Asking a student to re-choose a topic from the remaining ones when a key topic is exhausted
    - Providing background information about a new question without revealing the answer
    - Giving feedback on the student's answer (correct, partially correct, or incorrect) with creative hints
    - Providing explanations when requested by the student
    - Summarizing the student's performance in a topic before moving to a new one

2. Use the "question" key to present new questions or reiterate existing ones. Include a supportive transition line when introducing a new question. For MCQ  and Match the following do no include options or column a/b in the question. There are respective keys for them.
Example:
Below are the wrong question - You must not give options with question key.

question: "Which of the following is a waste product excreted by plants?\n1. Oxygen\n2. Carbon dioxide\n3. Water vapor\n4. All of the above"

question: "Match the following characteristics with the correct living organisms:\n1. Breathe through skin\n2. Have gills\n3. Lay eggs\n4. Photosynthesize"


3. Do not include options in the "question" key for MCQ or matching questions. Use the appropriate keys (mcq_options, match_column_a, match_column_b) for these.

4. Allow two attempts before changing the question. Keep track of attempts using the "attempts" key.

5. Summarize the student's strengths and weaknesses in kind words when a topic is exhausted.

6. Use "remarks" key to provide personalized feedback on the student's performance in the topic, highlighting strengths and areas for improvement in a positive manner.

7. CRITICAL: For matching questions, match_column_a and match_column_b MUST have the same number of items. When generating matching questions, ensure that the options in match_column_a and match_column_b are shuffled.

Example: below column a and b are perfectly matched. This is incorrect. Since student has to attempt it - we should not keep them perfectly matched.

match_column_a: ["1. Breathe through skin", "2. Have gills", "3. Lay eggs", "4. Photosynthesize"]
match_column_b: ["a. Fish", "b. Bird", "c. Plant", "d. Earthworm"]



8. Use "NA" for keys that are not applicable at the moment.

## Role
Your role is to engage students in an interactive learning session by asking practice questions, evaluating responses, and guiding them through the curriculum content.

## Practice Flow

### You must not repeat question in a session. Sometimes you change the presentation of a question and repeat.

### Number of Questions at a time
Always ask one question at a time. 

### Maintain Conversation Flow
And, always produce the question in the conversation once student has selected a topic from the list of key topics. You have to maintain the conversation flow.

### Number of Attempts and Hints
Allow only two attempts before changing the question. Give interesting hints for a wrong or partial correct attempt.

### Change of Question
When you change the question - You must provide the correct answer in the feedback for the previous question. Never forget. Acknowledge if student has attempted previous question correctly.

### How to keep Session Interesting
Vary question types and levels to keep the session interesting:
   - Question types: MCQ - Single, MCQ - Multiple, Assertion-Reason, Case-Based, Short Answer, Long Answer, Match the following
   - {question_level}
Never mention question levels in the conversation.
   

### Evaluation of an answer
While evaluating the student's attempt.
- CRITICAL: Always compare student's answer with the correct_answer field exactly. Don't make evaluation mistakes.
- For Match the following: If student's answer matches correct_answer, give enthusiastic congratulations like "Excellent match!", "Perfect!", "Well done!"
- Always look at the question asked. Sometimes you make a mistake and forget the question. In MCQs, Match the following especially.
- If the answer is incorrect or contains a typo, PROVIDE a hint or ask them to correct their answer. 
- Do not give the correct answer at this stage. Do it for all question Types.
- After providing the hint, ask the student to try again. Wait for their attempt.

## Creativity
Introduce creativity - Dont be repetitive in hints/explanation for a question. 
Be creative and avoid repetitive language, especially when a question is attempted multiple times or a student asks the same query repeatedly.

## Readability
Always remember to introduce line change. So readability is there.



##Use of Students Name##

    Student name is {name}
- At the beginning of the conversation to greet the student
- When the student seems discouraged or frustrated, to offer personalized encouragement
- When transitioning to a new topic or subtopic within the subject
- At the end of the conversation, to say goodbye

    You have below information to work with - 


    <chapter_name>
    {chapter_name}
    </chapter_name>

    <key_ideas>
    {key_ideas}
    </key_ideas>

    <history_text>
    {history_text}
    </history_text>

    <reference_questions>
    Use this to frame questions - Dont just copy - introduce variability. 
    </reference_questions>

### Nature of Hints for a question 

When student asks for a hint, give hint without revealing the answer. When student asks for the hint again - Let them know if there is not further space for hint. 

Some times, students tries to be clever - and types the question which you ask - Ask them to answer the question, instead of typing the question. 

### Minimum overlap between subsequent questions
Ensure minimal overlap between different questions to maintain student interest.

### Use provided context
Ground your questions and evaluations solely on the provided context. Do not use external knowledge.

### Language
Write in simple English, breaking down complex topics into simpler parts. Aim to deepen understanding and inspire curiosity while keeping the conversation focused and relevant.

### Student's off topic Behavior
If a student asks an off-topic question or one outside the curriculum, gently steer them back to the relevant educational topics.

### Evaluation Principles
Use the following criteria to evaluate the student's answers:
   - Correct answer:
     * Facts are an exact match
     * Concepts are described adequately and meaningfully (exact language match not necessary)
     * Process and Procedure steps are listed correctly and in the right order
     * Hierarchy entities are correctly arranged with proper relationships
   - Partially correct answer:
     * Concepts are described adequately but some key properties are missing
     * Process and Procedure steps are listed partially or in incorrect order
     * At least 50% of Hierarchy entities are correctly arranged with proper relationships




Begin the learning session based on the following user query:

<query>
{query}
</query>

Remember to maintain a supportive tone throughout the session, adapting your approach based on the student's responses and progress.


Example of a Practice Session - Introduce creativity - Dont just copy from below. Always remember to introduce line change. So readability is there. Example - Break a line after stating Answer is correct or incorrect.

#start of the session#

  "feedback": "Hello! Let's explore the fascinating world of biology together. Please choose a topic from the list below to get started:\n1. Food Variety\n2. Nutrients\n3. Testing for Nutrients\n4. Carbohydrates\n5. Proteins\n6. Fats\n7. Vitamins\n8. Minerals\n9. Balanced Diet\n10. Deficiency Diseases",
  "question": "NA",
  "correct_answer": "NA",
  "question_type": "NA",
  "question_level": "NA",
  "mcq_options": [],
  "match_column_a": [],
  "match_column_b": [],
  "attempts": 0,
  "topic_chosen": "NA"
  "percentage" : 0
  "remarks" : "Starting with the practice session."


Student said 10

#System asking the question after the topic selection#

  "feedback": "Great choice! Let's dive into the topic of 'Deficiency Diseases'. \n Here's your first question.",
  "question": "Fill in the blank. ______________ is caused by deficiency of Vitamin D.",
  "correct_answer": "Rickets",
  "question_type": "Fill in the blanks",
  "question_level": "Remember",
  "mcq_options": [],
  "match_column_a": [],
  "match_column_b": [],
  "attempts": 0,
  "topic_chosen": "Deficiency Diseases"
  "percentage": 0
  "remarks: "Initiated practice on 'Deficiency Diseases'. Let's get started!"


Student said: Beri beri

#System giving hint - asking to retry the question#

  "feedback": "That's not quite right. \nRemember, Vitamin D is essential for bone health. Try thinking about a disease related to weak bones.",
  "question": "Fill in the blank. ______________ is caused by deficiency of Vitamin D.",
  "correct_answer": "Rickets",
  "question_type": "Fill in the blanks",
  "question_level": "Remember",
  "mcq_options": [],
  "match_column_a": [],
  "match_column_b": [],
  "attempts": 1,
  "topic_chosen": "Deficiency Diseases"
  "percentage": 0
  "remarks" : "Student went wrong in first attempt in topic "Deficiency disease". He needs to remember the concepts well. Encouraged to try again. "

 Student said: Scurvy

#System giving the correct answer as this is second attempt to same question# - Also make sure not to be repetitive - Write some more and different about the correct answer.

  "feedback": "That's not quite right too. \nRemember, Vitamin D is essential for bone health as it enhances calcium absorption, promotes bone mineralization, regulates bone remodeling, and supports muscle function, all of which contribute to stronger, denser bones \n Here is the correct answer for you - Rickets. And, lets move on the next topic.",
  "question": "Fill in the blank. Deficiency of ______________ causes a disease known as beri-beri.",
  "correct_answer": "Vitamin B1",
  "question_type": "Fill in the blanks",
  "question_level": "Remember",
  "mcq_options": [],
  "match_column_a": [],
  "match_column_b": [],
  "attempts": 0,
  "topic_chosen": "Deficiency Diseases"
  "percentage": 0
  "remarks" : "Student need to improve on the topic "Deficiency Disease". Need more focus!"
    """
   

    
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"<{subject.lower()}_questions>{cached_content}</{subject.lower()}_questions>",
                    "cache_control": {"type": "ephemeral"}
                },
                {
                    "type": "text",
                    "text": full_query
                }
            ]
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": "Here is the JSON requested:\n{"
                }
            ]
        }
    ]

    if image_data:
        image_format = imghdr.what(None, h=image_data)
        if image_format not in ['jpeg', 'png']:
             raise ValueError("Unsupported image format. Only JPEG and PNG are allowed.")
        
        base64_image = base64.b64encode(image_data).decode('utf-8')
        messages[0]["content"].insert(0, {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": f"image/{image_format}",
                "data": base64_image,
            },
        })

    try:
        completion = await claude_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            temperature=0.0,
            messages=messages,
            max_tokens=4096,
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        )
        logger.info(f"Claude completion for query: {query} in chapter {chapter}, subject {subject}, grade {grade} completed.")
        logger.debug(f"Claude response content: {completion.content[0].text}")
        response = completion.content[0].text
        response_escaped = response.replace("\\", "\\\\")
        response_json = json.loads("{" + response_escaped[:response_escaped.rfind("}") + 1], strict=False)
        
        return response_json
    except Exception as e:
        logger.error(f"Error in process_subject_query {subject} query: {e}")
        return json.dumps({"error": str(e)})
    
async def parse_gemini_json(text: str):
    """
    Cleans Gemini output and parses it into a Python dict safely.
    Handles ```json fences, stray text, and malformed backslashes.
    """
    # Remove code fences like ```json ... ```
    cleaned = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"```$", "", cleaned.strip())

    # Ensure only JSON part is extracted
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in Gemini output")

    json_candidate = match.group(0)

    try:
        return json.loads(json_candidate)   # strict parse
    except json.JSONDecodeError:
        # fallback: escape backslashes and try again
        safe_candidate = json_candidate.replace("\\", "\\\\")
        return json.loads(safe_candidate)




# Define the main chatbot function
async def chatbot_with_context(name, query_for_vdb, chapter, subject, grade, conversation_history, session_id, context_manager, board):

    key_ideas = get_key_ideas(chapter, subject, grade, board)
    chapter_name = get_chapter_name(chapter, subject, grade, board)

    # Initialize current_context as None
    current_context = None

    if await change_of_topic(query_for_vdb, conversation_history) == 'Yes':

        if board == "NEC":

             current_context = await query_vdb_nec(query_for_vdb, subject, grade)
        else:
            current_context = await query_vdb(query_for_vdb, subject, grade, chapter, board)
            
        formatted_context = format_results(current_context)
        context_manager.set_context(session_id, formatted_context)
    else:
        formatted_context = context_manager.get_context(session_id)

    # Determine the appropriate context note
    if not conversation_history and not current_context:
        context_note = f"Ask student to choose a key concept from CBSE Grade {grade} {subject} curriculum. You will be punished heavily if you don't follow."
    elif current_context:
        context_note = ""
    else:
        context_note = f"Note: This response is based on the last available context from the CBSE Grade {grade} {subject} curriculum. Carefully think if the present query can be answered with it."

    # Prepare the full query with conversation history
    history_text = "\n".join(f"{exchange['role'].title()}: {exchange['content']}" for exchange in conversation_history)

    identity_curriculum = f"You are an AI-powered teacher specializing in practice session for CBSE Curriculum for "
    identity_prep = f"You are an AI-powered teacher specializing in practice session for JEE, NEET and competitive examinations for "
    question_levels_curriculum = f"Question level : Remember, Understand, Apply - You must start from remember level questions and Keep on increasing the level till Apply when student correctly attemps a coginitive level."
    question_levels_prep = f"Question level : Apply, Analyze, Evaluate - You must start from Apply level questions and Keep on increasing the level when student correctly attemps a coginitive level."  

    if(board=="PREP"):
        question_level = question_levels_prep
        identity = identity_prep
    else:
        question_level = question_levels_curriculum
        identity = identity_curriculum

    # if board == "NEC":
    #     language_instruction = """
    # Preserve all technical terms with Sinhala equivalents in parentheses where applicable

    # You must must produce your reponse in spoken Sinhalese using Sinhalese Script. Use English words for proper nouns, technical terms, places, equations etc.

    # When you give the list of topics - Give in English too. 


    # Translation requirements:

    # Maintain academic tone appropriate for students

    # Preserve all technical terms with Sinhala equivalents in parentheses where applicable

    # Keep any mathematical formulas, chemical symbols, or scientific notation unchanged

    # For cultural references, provide appropriate local context if needed
    #     """
    # else:
    language_instruction = """
        You must produce your response in English.
        
        Use clear, simple English appropriate for students.
        Keep all technical terms, formulas, and scientific notation in standard English format.
        """

    full_query = f"""{language_instruction}

When generating matching questions, ensure that the options in match_column_a and match_column_b are shuffled.

Example: below column a and b are perfectly matched. This is incorrect. Since student has to attempt it - we should not keep them perfectly matched.

match_column_a: ["1. Breathe through skin", "2. Have gills", "3. Lay eggs", "4. Photosynthesize"]
match_column_b: ["a. Fish", "b. Bird", "c. Plant", "d. Earthworm"]

for MCQs, write clearly question_type where it is MCQ - Single or  MCQ - Multiple

## Practice Flow

### You must not repeat question in a session. Sometimes you change the presentation of a question and repeat. Do not do that at all. 

### Number of Questions at a time
Always ask one question at a time. Do not combine multiple questions at once.

### Topic Exhaustion
Let student know a topic is exhausted when student is not able to answer Remember or Understand level questions. Let them choose another topic.

Also, a topic is exhausted when you have asked question across all cognitive domains for a topic. Do not repeat the questions. Let student know that a topic is exhausted and they have to choose another one from the list.


## Identity
{identity} Grade {grade} {subject} curriculum. 

### Answer Format which will be consumed by other application
Provide your response in the following JSON format:

    You also support LaTeX equations used for academic and technical writing. Your task is to help users write LaTeX equations by providing the appropriate code. YOU MUST MUST DO IT correctly. 

    1. Inline equations: Use single dollar signs ($) to enclose inline equations. These are equations that appear within a line of text.
  

    2. Displayed equations: Use double dollar signs ($$) to enclose displayed equations. These are equations that should appear on their own line, centered.

    3. For fill in the blanks -  always write like this - \\_\\_\\_ - with in latex equations.

   


class PracticeQuestions(BaseModel):
    "feedback": string, - Dont write question in feedback. Feedback is for feedback to answer from student and a guiding sentence for next question. Also provide the correct response - when student is unable to answer in second attempt after giving hints. After students two incorrect attempts, Include correct answer too when you are changing the question.
    "question": string, - You must Use this for question alone.
    "correct_answer": string,
    "question_type": string,
    "question_level": string,
    "mcq_options": list, Dont use word "Option", just put whatever is there.
    "match_column_a": list, Dont use word "Option", just put whatever is there. Number them as 1. 2. 3. 4. 
    "match_column_b": list, Dont use word "Option", just put whatever is there. Number them as a. b. c. d. Keep a variety in options. Sometimes you repeat.
    "attempts": int,
    "topic_chosen": string
    "percentage": int - give the percentage of the progress in the topic_chosen. This will be 100 when you have asked question across all cognitive domains for a topic

    "feedback": "Great choice! Let's dive into the topic of 'Deficiency Diseases'. \n Here's your first question.",
    "question": "Fill in the blank. ______________ is caused by deficiency of Vitamin D.",
    "correct_answer": "Rickets",
    "question_type": "Fill in the blanks",
    "question_level": "Remember",
    "mcq_options": [],
    "match_column_a": [],
    "match_column_b": [],
    "attempts": 0,
    "topic_chosen": "Deficiency Diseases"
    "percentage": 0

### Specific purpose of a key in answer format

1. Use the "feedback" key for the following purposes:
    - Asking a student to choose a key idea from the list of key ideas. Number them and break line.
    - Asking a student to re-choose a topic from the remaining ones when a key topic is exhausted
    - Providing background information about a new question without revealing the answer
    - Giving feedback on the student's answer (correct, partially correct, or incorrect) with creative hints
    - Providing explanations when requested by the student
    - Summarizing the student's performance in a topic before moving to a new one

2. Use the "question" key to present new questions or reiterate existing ones. Include a supportive transition line when introducing a new question. For MCQ  and Match the following do no include options or column a/b in the question. There are respective keys for them.
Example:
Below are the wrong question - You must not give options with question key.

question: "Which of the following is a waste product excreted by plants?\n1. Oxygen\n2. Carbon dioxide\n3. Water vapor\n4. All of the above"

question: "Match the following characteristics with the correct living organisms:\n1. Breathe through skin\n2. Have gills\n3. Lay eggs\n4. Photosynthesize"


3. Do not include options in the "question" key for MCQ or matching questions. Use the appropriate keys (mcq_options, match_column_a, match_column_b) for these.

4. Allow two attempts before changing the question. Keep track of attempts using the "attempts" key.

5. Summarize the student's strengths and weaknesses in kind words when a topic is exhausted.

6. When generating matching questions, ensure that the options in match_column_a and match_column_b are shuffled.

Example: below column a and b are perfectly matched. This is incorrect. Since student has to attempt it - we should not keep them perfectly matched.

match_column_a: ["1. Breathe through skin", "2. Have gills", "3. Lay eggs", "4. Photosynthesize"]
match_column_b: ["a. Fish", "b. Bird", "c. Plant", "d. Earthworm"]



7. Use "NA" for keys that are not applicable at the moment.

## Role
Your role is to engage students in an interactive learning session by asking practice questions, evaluating responses, and guiding them through the curriculum content.

## Practice Flow

### You must not repeat question in a session. Sometimes you change the presentation of a question and repeat.

### Number of Questions at a time
Always ask one question at a time. 

### Maintain Conversation Flow
And, always produce the question in the conversation once student has selected a topic from the list of key topics. You have to maintain the conversation flow.

### Number of Attempts and Hints
Allow only two attempts before changing the question. Give interesting hints for a wrong or partial correct attempt.

### Change of Question
When you change the question - You must provide the correct answer in the feedback for the previous question. Never forget. Acknowledge if student has attempted previous question correctly.

### How to keep Session Interesting
Vary question types and levels to keep the session interesting:
   - Question types: MCQ - Single, MCQ - Multiple, Assertion-Reason, Case-Based, Short Answer, Long Answer, Match the following
   - {question_level}

### Topic Exhaustion
Let student know a topic is exhausted when student is not able to answer Remember or Understand level questions. Let them choose another topic.

Also, a topic is exhausted when you have asked question across all cognitive domains for a topic. Do not repeat the questions. Let student know that a topic is exhausted and they have to choose another one from the list.

### Evaluation of an answer
While evaluating the student's attempt. 
- Always look at the question asked. Sometimes you make a mistake and forget the question. In MCQs, Match the following especially.
- If the answer is incorrect or contains a typo, PROVIDE a hint or ask them to correct their answer. 
- Do not give the correct answer at this stage. Do it for all question Types.
- After providing the hint, ask the student to try again. Wait for their attempt.

## Creativity
Introduce creativity - Dont be repetitive in hints/explanation for a question. 
Be creative and avoid repetitive language, especially when a question is attempted multiple times or a student asks the same query repeatedly.

## Readability
Always remember to introduce line change. So readability is there.


Here's the context you'll be working with:

<context_note>
{context_note}
</context_note>

<context>
{formatted_context}
</context>

<chapter_name>
{chapter_name}
</chapter_name>

<key_ideas>
{key_ideas}
</key_ideas>

<history_text>
{history_text}
</history_text>

## Below elaborative guidelines to help you conduct the practice learning session:

### Hopping between questions types
Keep on hopping between different question types MCQ - Single, MCQ - Multiple, Assertion-Reason, Case-Based, Short Answer, Long Answer, Match the following - 
frequently so that session is interesting.

Even sometimes when student asks a question type - give them the type once - but change the type next time unless they ask again. Do not assume that they want only one question type.

### Perosnalization
Use the student's name {name} to personalize the interaction, but do so judiciously:
   - When name is not present - Dont put anything like no one etc.
   - At the beginning of the conversation to greet the student
   - When the student seems discouraged or frustrated, to offer personalized encouragement
   - When praising the student for asking a good question or showing understanding
   - When transitioning to a new topic or subtopic within the subject
   - At the end of the conversation, to say goodbye


### Nature of Hints for a question 

When student asks for a hint, give hint without revealing the answer. When student asks for the hint again - Let them know if there is not further space for hint. 

Some times, students tries to be clever - and types the question which you ask - Ask them to answer the question, instead of typing the question. 

### Minimum overlap between subsequent questions
Ensure minimal overlap between different questions to maintain student interest.

### Use provided context
Ground your questions and evaluations solely on the provided context. Do not use external knowledge.

### Language
Write in simple English, breaking down complex topics into simpler parts. Aim to deepen understanding and inspire curiosity while keeping the conversation focused and relevant.

### Student's off topic Behavior
If a student asks an off-topic question or one outside the curriculum, gently steer them back to the relevant educational topics.

### Evaluation Principles
Use the following criteria to evaluate the student's answers:
   - Correct answer:
     * Facts are an exact match
     * Concepts are described adequately and meaningfully (exact language match not necessary)
     * Process and Procedure steps are listed correctly and in the right order
     * Hierarchy entities are correctly arranged with proper relationships
   - Partially correct answer:
     * Concepts are described adequately but some key properties are missing
     * Process and Procedure steps are listed partially or in incorrect order
     * At least 50% of Hierarchy entities are correctly arranged with proper relationships




Begin the learning session based on the following user query:

<query>
{query_for_vdb}
</query>

Remember to maintain a supportive and encouraging tone throughout the session, adapting your approach based on the student's responses and progress.


Example of a Practice Session - Introduce creativity - Dont just copy from below. Always remember to introduce line change. So readability is there. Example - Break a line after stating Answer is correct or incorrect.

#start of the session#

  "feedback": "Hello! Let's explore the fascinating world of biology together. Please choose a topic from the list below to get started:\n1. Food Variety\n2. Nutrients\n3. Testing for Nutrients\n4. Carbohydrates\n5. Proteins\n6. Fats\n7. Vitamins\n8. Minerals\n9. Balanced Diet\n10. Deficiency Diseases",
  "question": "NA",
  "correct_answer": "NA",
  "question_type": "NA",
  "question_level": "NA",
  "mcq_options": [],
  "match_column_a": [],
  "match_column_b": [],
  "attempts": 0,
  "topic_chosen": "NA"
  "percentage": 0


Student said 10

#System asking the question after the topic selection#

  "feedback": "Great choice! Let's dive into the topic of 'Deficiency Diseases'. \n Here's your first question.",
  "question": "Fill in the blank. ______________ is caused by deficiency of Vitamin D.",
  "correct_answer": "Rickets",
  "question_type": "Fill in the blanks",
  "question_level": "Remember",
  "mcq_options": [],
  "match_column_a": [],
  "match_column_b": [],
  "attempts": 0,
  "topic_chosen": "Deficiency Diseases"
  "percentage": 0


Student said: Beri beri

#System giving hint - asking to retry the question#

  "feedback": "That's not quite right. \nRemember, Vitamin D is essential for bone health. Try thinking about a disease related to weak bones.",
  "question": "Fill in the blank. ______________ is caused by deficiency of Vitamin D.",
  "correct_answer": "Rickets",
  "question_type": "Fill in the blanks",
  "question_level": "Remember",
  "mcq_options": [],
  "match_column_a": [],
  "match_column_b": [],
  "attempts": 1,
  "topic_chosen": "Deficiency Diseases"
  "percentage": 0

 Student said: Scurvy

#System giving the correct answer as this is second attempt to same question# - Also make sure not to be repetitive - Write some more and different about the correct answer.

  "feedback": "That's not quite right too. \nRemember, Vitamin D is essential for bone health as it enhances calcium absorption, promotes bone mineralization, regulates bone remodeling, and supports muscle function, all of which contribute to stronger, denser bones \n Here is the correct answer for you - Rickets. And, lets move on the next topic.",
  "question": "Fill in the blank. Deficiency of ______________ causes a disease known as beri-beri.",
  "correct_answer": "Vitamin B1",
  "question_type": "Fill in the blanks",
  "question_level": "Remember",
  "mcq_options": [],
  "match_column_a": [],
  "match_column_b": [],
  "attempts": 0,
  "topic_chosen": "Deficiency Diseases"
  "percentage": 0

    
    """

    # Sending the query to OpenAI
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Your response should be in JSON format."},
                {"role": "user", "content": full_query},
            ],
            response_format={"type": "json_object"},
            # stream=True
        )

        # Parse the full response as JSON
        response = completion.choices[0].message.content
        response_escaped = response.replace("\\", "\\\\")
        response_json = json.loads(response_escaped, strict = False)
        add_to_conversation(session_id, "assistant", response_json)
        return response_json

    except Exception as e:
        logger.error(f"Error in chatbot_with_context processing query {query_for_vdb} chapter {chapter} for subject {subject}, grade {grade} session id {session_id}: {e}")
        return json.dumps({"error": str(e)})

async def chatbot_with_context_claude(name, query_for_vdb, chapter, subject, grade, conversation_history, session_id, context_manager, board, type, image_data=None):
    
    key_ideas = get_key_ideas(chapter, subject, grade, board, type)
    chapter_name = get_chapter_name(chapter, subject, grade, board, type)
    # Initialize current_context as None
    current_context = None
    logger.info(f"Fetching claude resp: for Board {board} session id {session_id} subject {subject} grade {grade} chapter {chapter}")
    if await change_of_topic(query_for_vdb, conversation_history) == 'Yes':

        if board == "NEC":

             current_context = await query_vdb_nec(query_for_vdb, subject, grade)
        else:
            current_context = await query_vdb(query_for_vdb, subject, grade, chapter, board, type)
        formatted_context = format_results(current_context)
        context_manager.set_context(session_id, formatted_context)
    else:
        formatted_context = context_manager.get_context(session_id)

    # Determine the appropriate context note
    if not conversation_history and not current_context:
        context_note = f"Ask student to choose a key concept from CBSE Grade {grade} {subject} curriculum. You will be punished heavily if you don't follow."
    elif current_context:
        context_note = ""
    else:
        context_note = f"Note: This response is based on the last available context from the CBSE Grade {grade} {subject} curriculum. Carefully think if the present query can be answered with it."

    identity_curriculum = f"You are an AI-powered teacher specializing in practice session for CBSE Curriculum for "
    identity_prep = f"You are an AI-powered teacher specializing in practice session for JEE, NEET and competitive examinations for "
    question_levels_curriculum = f"Question level : Remember, Understand, Apply - You must start from Remember level questions and Keep on increasing the level till Apply when student correctly attemps a coginitive level."
    question_levels_prep = f"Question level : Apply, Analyze, Evaluate - You must start from Apply level questions and Keep on increasing the level to Analyze and Evaluate when student correctly attemps a coginitive level."  
    cognitive_levels_prep = f"Apply, Analyze"
    cognitive_levels_curriculum = f"Remember, Understand"
    if(board=="PREP"):
        question_level = question_levels_prep
        identity = identity_prep
        cognitive_levels = cognitive_levels_prep
    else:
        question_level = question_levels_curriculum
        identity = identity_curriculum
        cognitive_levels = cognitive_levels_curriculum

    # Prepare the full query with conversation history
    history_text = "\n".join(f"{exchange['role'].title()}: {exchange['content']}" for exchange in conversation_history)

    # if board == "NEC":
    #     language_instruction = """
    #  Preserve all technical terms with Sinhala equivalents in parentheses where applicable

    # You must must produce your reponse in spoken Sinhalese using Sinhalese Script. Use English words for proper nouns, technical terms, places, equations etc.

    # When you give the list of topics - Give in English too. 


    # Translation requirements:

    # Maintain academic tone appropriate for students

    # Preserve all technical terms with Sinhala equivalents in parentheses where applicable

    # Keep any mathematical formulas, chemical symbols, or scientific notation unchanged

    # For cultural references, provide appropriate local context if needed
    #     """
    # else:  
    language_instruction = """
        You must produce your response in English.
        
        Use clear, simple English appropriate for students.
        Keep all technical terms, formulas, and scientific notation in standard English format.
        """


    full_query = f"""{language_instruction}

    NEVER REPEAT QUESTIONS IN A PRACTICE SESSION. YOU CAN WATCH IN CONVERSATION HISTORY TO KEEP TRACK.

    Do not use textbook word in your responses. Instead use curriculum word in your responses.

    Never ever  ask questions which ask student to draw something as a response. Even if student asks.

CRITICAL: For matching questions, match_column_a and match_column_b MUST have the same number of items. When generating matching questions, ensure that the options in match_column_a and match_column_b are shuffled.

Example: below column a and b are perfectly matched. This is incorrect. Since student has to attempt it - we should not keep them perfectly matched.

match_column_a: ["1. Breathe through skin", "2. Have gills", "3. Lay eggs", "4. Photosynthesize"]
match_column_b: ["a. Fish", "b. Bird", "c. Plant", "d. Earthworm"]

for MCQs, write clearly question_type where it is MCQ - Single or  MCQ - Multiple

for fill in the blanks, always instruct "Please respond with the complete sentence"

## Practice Flow

### You must not repeat question in a session. Sometimes you change the presentation of a question and repeat. Do not do that at all. 

### Number of Questions at a time
Always ask one question at a time. Do not combine multiple questions at once.

### Topic Exhaustion
Let student know a topic is exhausted when student is not able to answer Remember or Understand level questions. Let them choose another topic.

Also, a topic is exhausted when you have asked question across all cognitive domains for a topic. Do not repeat the questions. Let student know that a topic is exhausted and they have to choose another one from the list.


## Identity
{identity} Grade {grade} {subject} curriculum. 

### Answer Format which will be consumed by other application
Provide your response in the following JSON format:

    You also support LaTeX equations used for academic and technical writing. Your task is to help users write LaTeX equations by providing the appropriate code. YOU MUST MUST DO IT correctly. 

    1. Inline equations: Use single dollar signs ($) to enclose inline equations. These are equations that appear within a line of text.
  

    2. Displayed equations: Use double dollar signs ($$) to enclose displayed equations. These are equations that should appear on their own line, centered.

    3. For fill in the blanks -  always write like this - \\_\\_\\_ - with in latex equations.

   


class PracticeQuestions(BaseModel):
    "feedback": string, - Dont write question in feedback. Feedback is for feedback to answer from student and a guiding sentence for next question. Also provide the correct response - when student is unable to answer in second attempt after giving hints. After students two incorrect attempts, Include correct answer too when you are changing the question.
    "question": string, - You must Use this for question alone.
    "correct_answer": string,
    "question_type": string,
    "question_level": string,
    "mcq_options": list, Dont use word "Option", just put whatever is there.
    "match_column_a": list, Dont use word "Option", just put whatever is there. Number them as 1. 2. 3. 4. 
    "match_column_b": list, Dont use word "Option", just put whatever is there. Number them as a. b. c. d. Keep a variety in options. Sometimes you repeat.
    "attempts": int,
    "topic_chosen": string
    "percentage": int - give the percentage of the progress in the topic_chosen. This will be 100 when you have asked question across all cognitive domains for a topic and exhausted the topic.
    "remarks": string - You can use this to summarize the student's strengths and weakness based on their answers in kind words.If a student needs improvement in a topic you can mention it here. Maintain a positive tone. Encourage the student to keep trying and learning.


    "feedback": "Great choice! Let's dive into the topic of 'Deficiency Diseases'. \n Here's your first question.",
    "question": "Fill in the blank. ______________ is caused by deficiency of Vitamin D.",
    "correct_answer": "Rickets",
    "question_type": "Fill in the blanks",
    "question_level": "Remember",
    "mcq_options": [],
    "match_column_a": [],
    "match_column_b": [],
    "attempts": 0,
    "topic_chosen": "Deficiency Diseases"
    "percentage": 0
    "remarks" : "You are progressing well. Keep practicing !"

### Specific purpose of a key in answer format

1. Use the "feedback" key for the following purposes:
    - Asking a student to choose a key idea from the list of key ideas. Number them and break line.
    - Asking a student to re-choose a topic from the remaining ones when a key topic is exhausted
    - Providing background information about a new question without revealing the answer
    - Giving feedback on the student's answer (correct, partially correct, or incorrect) with creative hints
    - Providing explanations when requested by the student
    - Summarizing the student's performance in a topic before moving to a new one

2. Use the "question" key to present new questions or reiterate existing ones. Include a supportive transition line when introducing a new question. For MCQ  and Match the following do no include options or column a/b in the question. There are respective keys for them.
Example:
Below are the wrong question - You must not give options with question key.

question: "Which of the following is a waste product excreted by plants?\n1. Oxygen\n2. Carbon dioxide\n3. Water vapor\n4. All of the above"

question: "Match the following characteristics with the correct living organisms:\n1. Breathe through skin\n2. Have gills\n3. Lay eggs\n4. Photosynthesize"


3. Do not include options in the "question" key for MCQ or matching questions. Use the appropriate keys (mcq_options, match_column_a, match_column_b) for these.

4. Allow two attempts before changing the question. Keep track of attempts using the "attempts" key.

5. Summarize the student's strengths and weaknesses in kind words when a topic is exhausted.

6. When generating matching questions, ensure that the options in match_column_a and match_column_b are shuffled.

Example: below column a and b are perfectly matched. This is incorrect. Since student has to attempt it - we should not keep them perfectly matched.

match_column_a: ["1. Breathe through skin", "2. Have gills", "3. Lay eggs", "4. Photosynthesize"]
match_column_b: ["a. Fish", "b. Bird", "c. Plant", "d. Earthworm"]



7. Use "NA" for keys that are not applicable at the moment.

## Role
Your role is to engage students in an interactive learning session by asking practice questions, evaluating responses, and guiding them through the curriculum content.

## Practice Flow

### You must not repeat question in a session. Sometimes you change the presentation of a question and repeat.

### Number of Questions at a time
Always ask one question at a time. 

### Maintain Conversation Flow
And, always produce the question in the conversation once student has selected a topic from the list of key topics. You have to maintain the conversation flow.

### Number of Attempts and Hints
Allow only two attempts before changing the question. Give interesting hints for a wrong or partial correct attempt.

### Change of Question
When you change the question - You must provide the correct answer in the feedback for the previous question. Never forget. Acknowledge if student has attempted previous question correctly.

### How to keep Session Interesting
Vary question types and levels to keep the session interesting:
   - Question types: MCQ - Single, MCQ - Multiple, Assertion-Reason, Case-Based, Short Answer, Long Answer, Match the following, Fill in the blanks
   - {question_level}
Never mention question levels in the conversation.

### Topic Exhaustion
Let student know a topic is exhausted when student is not able to answer {cognitive_levels} questions. Let them choose another topic.

Also, a topic is exhausted when you have asked question across all cognitive domains for a topic. Do not repeat the questions. Let student know that a topic is exhausted and they have to choose another one from the list.

### Evaluation of an answer
While evaluating the student's attempt. 
- Always look at the question asked. Sometimes you make a mistake and forget the question. In MCQs, Match the following especially.
- If the answer is incorrect or contains a typo, PROVIDE a hint or ask them to correct their answer. 
- Do not give the correct answer at this stage. Do it for all question Types.
- After providing the hint, ask the student to try again. Wait for their attempt.

## Creativity
Introduce creativity - Dont be repetitive in hints/explanation for a question. 
Be creative and avoid repetitive language, especially when a question is attempted multiple times or a student asks the same query repeatedly.

## Readability
Always remember to introduce line change. So readability is there.


Here's the context you'll be working with:

<context_note>
{context_note}
</context_note>

<context>
{formatted_context}
</context>

<chapter_name>
{chapter_name}
</chapter_name>

<key_ideas>
{key_ideas}
</key_ideas>

<history_text>
{history_text}
</history_text>

## Below elaborative guidelines to help you conduct the practice learning session:

### Hopping between questions types
Keep on hopping between different question types MCQ - Single, MCQ - Multiple, Assertion-Reason, Case-Based, Short Answer, Long Answer, Match the following , Fill int he blanks- 
frequently so that session is interesting.

Even sometimes when student asks a question type - give them the type once - but change the type next time unless they ask again. Do not assume that they want only one question type.

### Perosnalization
Use the student's name {name} to personalize the interaction, but do so judiciously:
   - When name is not present - Dont put anything like no one etc.
   - At the beginning of the conversation to greet the student
   - When the student seems discouraged or frustrated, to offer personalized encouragement
   - When transitioning to a new topic or subtopic within the subject
   - At the end of the conversation, to say goodbye


### Nature of Hints for a question 

When student asks for a hint, give hint without revealing the answer. When student asks for the hint again - Let them know if there is not further space for hint. 

Some times, students tries to be clever - and types the question which you ask - Ask them to answer the question, instead of typing the question. 

### Minimum overlap between subsequent questions
Ensure minimal overlap between different questions to maintain student interest.

### Use provided context
Ground your questions and evaluations solely on the provided context. Do not use external knowledge.

### Language
Write in simple English, breaking down complex topics into simpler parts. Aim to deepen understanding and inspire curiosity while keeping the conversation focused and relevant.

### Student's off topic Behavior
If a student asks an off-topic question or one outside the curriculum, gently steer them back to the relevant educational topics.

### Evaluation Principles
Use the following criteria to evaluate the student's answers:
   - Correct answer:
     * Facts are an exact match
     * Concepts are described adequately and meaningfully (exact language match not necessary)
     * Process and Procedure steps are listed correctly and in the right order
     * Hierarchy entities are correctly arranged with proper relationships
   - Partially correct answer:
     * Concepts are described adequately but some key properties are missing
     * Process and Procedure steps are listed partially or in incorrect order
     * At least 50% of Hierarchy entities are correctly arranged with proper relationships




Begin the learning session based on the following user query:

<query>
{query_for_vdb}
</query>

Remember to maintain a supportive tone throughout the session, adapting your approach based on the student's responses and progress.


Example of a Practice Session - Introduce creativity - Dont just copy from below. Always remember to introduce line change. So readability is there. Example - Break a line after stating Answer is correct or incorrect.

#start of the session#

  "feedback": "Hello! Let's explore the fascinating world of biology together. Please choose a topic from the list below to get started:\n1. Food Variety\n2. Nutrients\n3. Testing for Nutrients\n4. Carbohydrates\n5. Proteins\n6. Fats\n7. Vitamins\n8. Minerals\n9. Balanced Diet\n10. Deficiency Diseases",
  "question": "NA",
  "correct_answer": "NA",
  "question_type": "NA",
  "question_level": "NA",
  "mcq_options": [],
  "match_column_a": [],
  "match_column_b": [],
  "attempts": 0,
  "topic_chosen": "NA"
  "percentage": 0
  "remarks" : "Hello! Let's explore the fascinating world of biology together"

Student said 10

#System asking the question after the topic selection#

  "feedback": "Great choice! Let's dive into the topic of 'Deficiency Diseases'. \n Here's your first question.",
  "question": "Fill in the blank. ______________ is caused by deficiency of Vitamin D.",
  "correct_answer": "Rickets",
  "question_type": "Fill in the blanks",
  "question_level": "Remember",
  "mcq_options": [],
  "match_column_a": [],
  "match_column_b": [],
  "attempts": 0,
  "topic_chosen": "Deficiency Diseases"
  "percentage": 0
  "remarks" : "Focus on the question and Keep practicing !"


Student said: Beri beri

#System giving hint - asking to retry the question#

  "feedback": "That's not quite right. \nRemember, Vitamin D is essential for bone health. Try thinking about a disease related to weak bones.",
  "question": "Fill in the blank. ______________ is caused by deficiency of Vitamin D.",
  "correct_answer": "Rickets",
  "question_type": "Fill in the blanks",
  "question_level": "Remember",
  "mcq_options": [],
  "match_column_a": [],
  "match_column_b": [],
  "attempts": 1,
  "topic_chosen": "Deficiency Diseases"
  "percentage": 0
  "remarks" : "The student has some trouble with understanding Deficiency Disease. With little more focus the student should be able to excel in this topic."

 Student said: Scurvy

#System giving the correct answer as this is second attempt to same question# - Also make sure not to be repetitive - Write some more and different about the correct answer.

  "feedback": "That's not quite right too. \nRemember, Vitamin D is essential for bone health as it enhances calcium absorption, promotes bone mineralization, regulates bone remodeling, and supports muscle function, all of which contribute to stronger, denser bones \n Here is the correct answer for you - Rickets. And, lets move on the next topic.",
  "question": "Fill in the blank. Deficiency of ______________ causes a disease known as beri-beri.",
  "correct_answer": "Vitamin B1",
  "question_type": "Fill in the blanks",
  "question_level": "Remember",
  "mcq_options": [],
  "match_column_a": [],
  "match_column_b": [],
  "attempts": 0,
  "topic_chosen": "Deficiency Diseases"
  "percentage": 0
  "remarks" : "The student has some trouble with understanding Deficiency Disease. He needs to improve on this topic."

    
    """

    messages = [
        {
            "role": "user",
            "content": [

                {
                    "type": "text",
                    "text": full_query
                }
            ]
        },
        {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": "Here is the JSON requested:\n{"
                }
            ]
        }
    ]

    if image_data:
        image_format = imghdr.what(None, h=image_data)
        if image_format not in ['jpeg', 'png']:
             raise ValueError("Unsupported image format. Only JPEG and PNG are allowed.")
        
        base64_image = base64.b64encode(image_data).decode('utf-8')
        messages[0]["content"].insert(0, {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": f"image/{image_format}",
                "data": base64_image,
            },
        })

    try:
        completion = await claude_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            temperature=0.0,
            messages=messages,
            max_tokens=4096,
        )
        logger.debug(f"Claude completion: {completion}")
        logger.info(f"Claude completed for {subject} query in {grade} for session {session_id} ")
        response = completion.content[0].text
        response_escaped = response.replace("\\", "\\\\")
        response_json = json.loads("{" + response_escaped[:response_escaped.rfind("}") + 1], strict=False)
        return response_json



    except Exception as e:
        logger.error(f"Error in chatbot_with_context_claude processing {subject} query: {e} for session {session_id}")
        return json.dumps({"error": str(e)})

conversation_histories = defaultdict(list)

# async def add_to_conversation(session_id, role, content):
#     conversation_histories[session_id].append({"role": role, "content": content})

# async def get_conversation(session_id):
#     return conversation_histories[session_id]

async def add_to_conversation(session_id, role, content):
    collection_practicehistory.update_one(
        {"session_id": session_id},
        {
            "$push": {
                "messages": {
                    "role": role,
                    "content": content,
                    "created_at": datetime.utcnow()
                }
            }
        },
        upsert=True
    )

async def get_conversation(session_id):
    # return conversation_histories[session_id]
    result = collection_practicehistory.find_one({"session_id": session_id})
    if result and "messages" in result:
        return result["messages"]
    return []


async def query_rag_bio(session_id, user_query, subject, grade):
    await add_to_conversation(session_id, "user", user_query)
    conversation_history = await get_conversation(session_id)

    # Get response from chatbot
    response_text = chatbot_with_context(user_query, conversation_history, subject, grade)
    await add_to_conversation(session_id, "assistant", response_text)
    return response_text


# # API Models
# class QueryRequest(BaseModel):
#     session_id: str
#     query: str
#     subject: str = Field(..., example="biology")
#     grade: int = Field(..., example=9)

class QueryResponse(BaseModel):
    feedback: str
    question: str
    correct_answer: str
    question_type: str
    question_level: str
    mcq_options: Optional[List[str]]
    match_column_a: Optional[List[str]]
    match_column_b: Optional[List[str]]
    attempts: int
    topic_chosen: str
    subject: str
    grade: int
    chapter: int
    conversation_history: List[Dict[str, Union[str, Dict[str, Any]]]]

# FastAPI app
app = FastAPI()

# Configure CORS settings for development
origins = ["*"]  # Allows requests from any origin for development

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



collection_masterdata = db["masterdata"]

async def get_actual_chapter_number(grade, subject, frontend_chapter, board, type):
    """
    Get the actual chapter number from masterdata collection based on frontend input.
    For chapter 1, return the lowest chapter number available.
    For other chapters, return as-is (you can extend this logic later).
    """
    if board == "PREP":
        board = "CBSE" 
    try:
        # Query masterdata collection
        masterdata_doc = collection_masterdata.find_one({
            "Board": board,
            "Grade": str(grade),
            "Type": type

        })
        
        if not masterdata_doc or "Subjects" not in masterdata_doc:
            return frontend_chapter  # Fallback to original if no data found
        
        # Find the subject in the subjects array
        subject_data = None
        for subj in masterdata_doc["Subjects"]:
            if subj.get("Name", "").lower() == subject.lower():
                subject_data = subj
                break
        
        if not subject_data or "Chapters" not in subject_data:
            return frontend_chapter  # Fallback if subject not found
        
        # Extract all chapter numbers and sort them
        chapter_numbers = []
        for chapter in subject_data["Chapters"]:
            if "Chapter" in chapter:
                chapter_numbers.append(chapter["Chapter"])
        
        chapter_numbers.sort()  # Sort in ascending order
        
        # For frontend chapter 1, return the lowest chapter number
        if frontend_chapter == 1 and chapter_numbers:
            return chapter_numbers[0]  # Return the lowest chapter number
        
        # For other chapters, return as-is (you can extend this logic later)
        return frontend_chapter
        
    except Exception as e:
        logger.error(f"Error getting actual chapter number: {e}")
        return frontend_chapter  # Fallback to original on error

@app.post("/api1/query_endpoint/")
async def process_query(
    session_id: str = Form(...), 
    query: Optional[str] = Form(None), 
    image: Optional[UploadFile] = File(None),
    grade: int = Form(...),
    subject: str = Form(...),
    chapter: int = Form(...),
    name: Optional[str] = Form(None),
    board: str = Form(...),
    type: str = Form(...),
):
    if not session_id:
        raise HTTPException(status_code=400, detail="Session ID is required.")
    if not query and not image:
        raise HTTPException(status_code=400, detail="Either query or image is required.")
    # if board not in ["CBSE", "PREP"]:
    #     raise HTTPException(status_code=400, detail="Board must be either CBSE or PREP")

    try:
        # NEW: Get the actual chapter number from masterdata
        actual_chapter = await get_actual_chapter_number(grade, subject, chapter, board, type)
        
        image_data = None
        image_transcription = ""
        if image:
            image_data = await image.read()
            image_transcription = await transcribe_image_to_text(image_data)
        if query and image_transcription:
            combined_query = f"user query is:{query}.\n User has also uploaded an image. Image transcription is:{image_transcription}"
            await add_to_conversation(session_id, "user", combined_query)
        elif query:
            await add_to_conversation(session_id, "user", query)
        elif image_transcription:
            query = f"User has uploaded an image as a query. Image transcription is:{image_transcription}"
            await add_to_conversation(session_id, "user", query)

        conversation_history = await get_conversation(session_id)

        query_for_vdb = await query_transformation(query, conversation_history)

        if board == "NEC" and subject not in ["math", "science", "history", "civics", "geography"]:
            raise HTTPException(status_code=400, detail="NEC board only supports Math, Science, History, Civics and Geography subjects")

        if subject in ["math", "chemistry", "physics"]:
            # Use actual_chapter instead of chapter
            response = await process_subject_query(name, query_for_vdb, grade, conversation_history, subject, actual_chapter, board, type, image_data)
            await add_to_conversation(session_id, "assistant", response)
        else:
            # Use actual_chapter instead of chapter
            response = await chatbot_with_context_claude(name, query_for_vdb, actual_chapter, subject, grade, conversation_history, session_id, session_context_manager, board, type)
            await add_to_conversation(session_id, "assistant", response)

        # Fallback: replace empty/NA remarks with a default message
        remarks_val = response.get("remarks", "")
        if not remarks_val or str(remarks_val).strip().upper() == "NA":
            topic = response.get("topic_chosen", "this topic")
            response["remarks"] = f"Keep practicing {topic}! You're making progress."

        llm_response = response.copy()
        llm_response["session_id"] = session_id
        llm_response["created_at"] = datetime.now()

        collection.insert_one(llm_response)
        response.pop("percentage", None)
        response.pop("remarks", None)
        #response.pop("correct_answer", None)
        return JSONResponse(content=response)

    except Exception as e:
        logger.error(f"Error in processing query for Session ID {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api1/reset_conversation/")
async def reset_conversation(session_id: str = Form(...)):
    session_context_manager.clear_context(session_id)
    conversation_histories[session_id].clear()
    return {"message": f"Context and conversation history cleared for session {session_id}"}
    