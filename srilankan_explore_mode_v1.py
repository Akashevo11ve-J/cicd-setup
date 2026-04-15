'''Explore mode with board as a parameter - allows different boards now'''

import base64
from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import time as time_module
from pydantic import BaseModel, Field
from typing import List, Dict, Union, Any, Optional

import os
from datetime import datetime

from pinecone import Pinecone
import asyncio

import openai
from openai import AsyncOpenAI

import logging
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from pymongo import MongoClient
from google.genai import Client

import imghdr

import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from anthropic import AsyncAnthropic

from collections import defaultdict
import threading
import re
import json
from whatsapp_helper import whatsapp_process_subject_query, whatsapp_process_nec_math_query, whatsapp_chatbot_with_context_nec, whatsapp_chatbot_with_context, whatsapp_process_nec_science
# Current date and time
now = datetime.now()
# import vertexai
# from vertexai.generative_models import (
#     GenerativeModel,
#     Part,
#     HarmCategory,
#     HarmBlockThreshold,
#     Tool
# )
# from vertexai.generative_models import (
#     Content
# )
# from vertexai.generative_models import (
#     FunctionDeclaration
# )

start = time_module.monotonic()
# some processing
executor = ThreadPoolExecutor(max_workers=4)
ai_executor = ThreadPoolExecutor(max_workers=4)

#Setup rotating file handler for logging
log_file_handler = RotatingFileHandler('app_logs.log', maxBytes=10000000, backupCount=5, encoding='utf-8')
#logger.basicConfig(handlers=[log_file_handler], level=logger.INFO, format='%(asctime)s - %(levelname)s - PID:%(process)d - Thread:%(threadName)s - %(message)s')
log_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - PID:%(process)d - Thread:%(threadName)s - %(message)s'))
logger = logging.getLogger()
logger.addHandler(log_file_handler)
logger.setLevel(logging.INFO)

logger.info(f"starting srilankan explore mode {start}")

# Load .env
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY missing in .env file")

DB_NAME = os.environ.get("DB_NAME")
# MongoDB setup
MONGO_URL = os.environ.get("MONGO_DB_URI")
client = MongoClient(MONGO_URL)
db = client[DB_NAME]  
collection = db.explore_chat_history


# Claude client
claude_client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Setup rotating file handler for logging
#log_file_handler = RotatingFileHandler('app_logs.log', maxBytes=10000000, backupCount=5)
#logger.basicConfig(handlers=[log_file_handler], level=logger.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define the index name
index_name = os.environ.get("EXPLORE_MODE_PCINDEX")
pc_api_key = os.environ.get("PINECONE_API_KEY")
video_index_name  = os.environ.get("VIDEO_PCINDEX")

# Initialize Pinecone
pc = Pinecone(api_key=pc_api_key)
index = pc.Index(host='https://dev-explore-cbse-ncert-textbooks-4a165ge.svc.aped-4627-b74a.pinecone.io')

genai_client = Client(api_key=API_KEY)

# Set up OpenAI API Key
#os.environ["OPENAI_API_KEY"] = KEY
openai.api_key = os.environ.get("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
#os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\vaish\creds\ivory-streamer-473110-e4-06c911548777.json"

#google_creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# Set the Google credentials for Vertex AI
#os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = google_creds_path

# Define API keys for different Pinecone environments

# Can be commented out
# PINECONE_API_KEYS = {
#     "subjects_9_10_11_12": "e849bc30-136c-4ca0-a1d5-151ac14ec2b3",
#     "subjects_6_7": "29cd36a6-3d40-4c97-bbd0-4de358dd3775",
#     "biology_11": "dcd21dc3-be0a-44c3-b0ad-73127bb04eb7"
# }


# # Initialize Pinecone instances
# pinecone_instances = {}

# for env, api_key in PINECONE_API_KEYS.items():
#     pinecone_instances[env] = Pinecone(api_key=api_key)

# def get_pinecone_instance(subject, grade):
#     grade = int(grade)
#     subject = subject.lower()

#     if grade in [6, 7]:
#         return pinecone_instances['subjects_6_7']
#     elif grade == 8 or (subject == 'biology' and grade == 11):
#         return pinecone_instances['biology_11']
#     elif grade in [9, 10, 11, 12]:
#         return pinecone_instances['subjects_9_10_11_12']
#     else:
#         raise ValueError(f"Unsupported grade: {grade}")

# pc = Pinecone(api_key="29cd36a6-3d40-4c97-bbd0-4de358dd3775")

# index_name = "biocbse9"

# index = pc.Index(index_name)

BOARD_INDEX_MAP = {
    "CBSE": os.environ.get("EXPLORE_MODE_PCINDEX"),
    "PREP": os.environ.get("EXPLORE_MODE_PCINDEX"),
    "NEC": os.environ.get("EXPLORE_MODE_PCINDEX"),
    "SSC-BSET": os.environ.get("SSC_BSET"),
    "IGCSE": os.environ.get("EXPLORE_MODE_PCINDEX"), # For working sake
    "NIOS": os.environ.get("EXPLORE_MODE_PCINDEX") # For working sake
}

async def get_embedding(text, model="text-embedding-ada-002"):
    loop = asyncio.get_event_loop()
    """Generate embeddings for a given text using a specified model."""
    resp = await loop.run_in_executor (ai_executor, lambda: openai.embeddings.create(input=[text], model=model))
    return resp.data[0].embedding

def build_filters(subject, grade, type):
    """
    Builds the lower and higher grade filters based on the provided grade.
    
    Parameters:
    - subject: The subject domain for the query (e.g., 'biology').
    - grade: The grade level for the query (e.g., '10').
    
    Returns:
    A tuple of dictionaries representing the lower grade filter and the higher grade filter.
    """
    grade = float(grade)
    if grade <= 10:
        hr_grade = grade + 2
    else:
        hr_grade = 12
    
    # Lower grade filter construction
    if grade == 6:
        lower_grade_filter = {
            "subject": {"$eq": subject.title()},
            "grade": {"$eq": 6.0},
            "type": {"$eq": type} 
        }
    else:
        lower_grade_filter = {
            "subject": {"$eq": subject.title()},
            "grade": {"$lte": grade, "$gte": 6.0},
            "type": {"$eq": type} 
        }
    
    # Higher grade filter construction
    if grade >= 12:
        higher_grade_filter = None  # No higher grades to search
    else:
        higher_grade_filter = {
            "subject": {"$eq": subject.title()},
            "grade": {"$gt": grade, "$lte": hr_grade},
            "type": {"$eq": type} 
        }
    
    return lower_grade_filter, higher_grade_filter


def build_filters_nec(subject, grade, type):
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
            "grade": {"$eq": 6.0},
            "type": {"$eq": type}
        }
    else:
        lower_grade_filter = {
            "subject": {"$eq": subject.lower()},
            "grade": {"$lte": grade, "$gte": 6.0},
            "type": {"$eq": type}
        }
    
    # Higher grade filter construction
    if grade >= 10:
        higher_grade_filter = None  # No higher grades to search
    else:
        higher_grade_filter = {
            "subject": {"$eq": subject.lower()},
            "grade": {"$gt": grade, "$lte": 10.0},  # Excludes the current grade by using $gt
            "type": {"$eq": type} 
        }
    
    return lower_grade_filter, higher_grade_filter

def get_subjects_for_board_grade(board, grade, type_param):
    try:
        # json_path = r"D:\AI-Scripts-on-Server\curriculum.json" 
        json_path = f"/home/ubuntu/main_apis/curriculum.json"
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for entry in data:
            if (entry.get("Category") == "Chapters" and 
                entry.get("Board") == board and 
                entry.get("Grade") == str(grade) and 
                entry.get("Type") == type_param):
                
                subjects = entry.get("Subjects", [])
                subject_names = [s.get("Name").capitalize() for s in subjects if s.get("Name")]
                
                logger.info(f"Loaded subjects: {subject_names}")
                return subject_names
        
        # Fallback
        return ["Biology", "History", "Civics", "Geography", "Math", "Physics", "Chemistry"]
        
    except Exception as e:
        logger.error(f"Error loading subjects: {e}")
        return ["Biology", "History", "Civics", "Geography", "Math", "Physics", "Chemistry"]
    

async def query_vdb(query, subject, board, grade, type, embed_model='text-embedding-ada-002', top_k=7, whatsapp=False):
    """
    Queries a vector database for text and related images using subject- and grade-specific filters.
    
    Parameters:
    - query: The query string.
    - subject: The subject domain for the query (e.g., 'biology').
    - grade: The grade level for the query (e.g., '10').
    - embed_model: The embedding model to use for generating embeddings.
    - top_k: The number of top matches to retrieve.
    - whatsapp: If True, skip image and video fetching.
    
    Returns:
    A dictionary with 'lower_grade_contexts', 'higher_grade_contexts', 'images', and 'videos'
    where each contains up to top_k matches, or None if no matches are found.
    """
    # Generate an embedding of the query using the specified model.
    embedding = await get_embedding(query, model=embed_model)
    logging.debug("Embedding Completed")

    index_name = BOARD_INDEX_MAP.get(board.upper())
    image_index_name = os.environ.get("EXPLORE_MODE_PCINDEX") 
    # Define the index name
    #index_name = "dev-explore-cbse-ncert-textbooks"

    def query_index(metadata_filter):
        logger.info(f"\nQuerying index with filter: {metadata_filter}")
        index = pc.Index(index_name)
        res = index.query(vector=embedding, filter=metadata_filter, top_k=top_k, include_metadata=True)
        filtered_matches = list(filter(lambda match: match['score'] > 0.75, res['matches']))
        return [{
            'text': match['metadata'].get('text', ''),
            'grade': match['metadata'].get('grade', ''),
            'subject': match['metadata'].get('subject', '')
        } for match in filtered_matches]
    
    def query_video_index(metadata_filter):
        logger.info(f"\nQuerying video index with filter: {metadata_filter}")
        video_idx = pc.Index(video_index_name) 

        res = video_idx.query(vector=embedding, filter=metadata_filter, top_k=top_k, include_metadata=True)
        filtered_matches = list(filter(lambda match: match['score'] > 0.50, res['matches']))
        logger.info(f"Found {len(filtered_matches)} video matches after filtering")
        return [{
            'text': match['metadata'].get('text', ''),
            'grade': match['metadata'].get('grade', ''),
            'subject': match['metadata'].get('subject', ''),
            'video_name': match['metadata'].get('video_name', ''),
        } for match in filtered_matches]
    def query_image_index(metadata_filter):
        logger.info(f"\nQuerying IMAGE index with filter: {metadata_filter}")
        index = pc.Index(image_index_name)
        res = index.query(vector=embedding, filter=metadata_filter, top_k=top_k, include_metadata=True)
        filtered_matches = list(filter(lambda match: match['score'] > 0.75, res['matches']))
        return [{
            'text': match['metadata'].get('text', ''),
            'grade': match['metadata'].get('grade', ''),
            'subject': match['metadata'].get('subject', '')
        } for match in filtered_matches]
    
    # Build lower and higher grade filters using the helper function
    lower_grade_filter, higher_grade_filter = build_filters(subject, grade, type)

    grade_float = float(grade)
    # hr_grade = grade_float + 2 if grade_float <= 10 else 12

    if grade <= 10:
        hr_grade = grade + 1
    else:
        hr_grade = 12
        
    image_filter = {
        "subject": {"$eq": subject.lower() + "_images"}, 
        "grade": {"$lte": hr_grade, "$gte": grade_float} 
    }

    video_filter = {
        "subject": {"$eq": subject.lower() + "_videos"}, 
        "grade": {"$eq": grade}
    }
    
    # Query indices in parallel
    if whatsapp:
        # Skip image and video queries for WhatsApp
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_filter = {
                executor.submit(query_index, lower_grade_filter): 'lower_grade_contexts',
                executor.submit(query_index, higher_grade_filter): 'higher_grade_contexts',
            }
            
            results = {}
            for future in concurrent.futures.as_completed(future_to_filter):
                filter_name = future_to_filter[future]
                try:
                    results[filter_name] = future.result()
                except Exception as exc:
                    logger.error(f'{filter_name} generated an exception: {exc}')
                    results[filter_name] = None
            
            # Set images and videos to None for WhatsApp
            results['images'] = None
            results['videos'] = None
    else:
        start_all = time_module.time()
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit all 4 at once
            start_lower = time_module.time()
            lower_future = executor.submit(query_index, lower_grade_filter)
            
            start_higher = time_module.time()
            higher_future = executor.submit(query_index, higher_grade_filter)
            
            start_images = time_module.time()
            images_future = executor.submit(query_image_index, image_filter)
            
            start_videos = time_module.time()
            videos_future = executor.submit(query_video_index, video_filter)
            
            # Get results with timing
            lower_result = lower_future.result()
            lower_time = time_module.time() - start_lower
            
            higher_result = higher_future.result()
            higher_time = time_module.time() - start_higher
            
            images_result = images_future.result()
            images_time = time_module.time() - start_images
            
            videos_result = videos_future.result()
            videos_time = time_module.time() - start_videos
            
            total_time = time_module.time() - start_all
            
            # logger.info timings
            logger.info(f"\nTASK TIMINGS:")
            logger.info(f"   LOWER_GRADE:  {lower_time:.2f}s")
            logger.info(f"   HIGHER_GRADE: {higher_time:.2f}s")
            logger.info(f"   IMAGES:       {images_time:.2f}s")
            logger.info(f"   VIDEOS:       {videos_time:.2f}s")
            logger.info(f"   TOTAL:        {total_time:.2f}s\n")
            
            results = {
                'lower_grade_contexts': lower_result,
                'higher_grade_contexts': higher_result,
                'images': images_result,
                'videos': videos_result
            }
            
            # Collect results as they complete
            try:
                results = {
                    'lower_grade_contexts': lower_future.result(),
                    'higher_grade_contexts': higher_future.result(),
                    'images': images_future.result(),
                    'videos': videos_future.result()
                }
            except Exception as exc:
                logger.error(f'Exception occurred: {exc}')
                results = {
                    'lower_grade_contexts': None,
                    'higher_grade_contexts': None,
                    'images': None,
                    'videos': None
                }
    logger.info(f"\n{'='*80}")
    logger.info(f"RAG RESULTS FOR SESSION")
    logger.info(f"{'='*80}")
    logger.info(f"Query: {query}")
    logger.info(f"Subject: {subject.title()}, Grade: {grade}, Board: {board}")
    logger.info(f"Lower Grade Contexts: {results.get('lower_grade_contexts', [])}")
    logger.info(f"Higher Grade Contexts: {results.get('higher_grade_contexts', [])}")
    logger.info(f"Images: {results.get('images', [])}")
    logger.info(f"Videos: {results.get('videos', [])}")
    logger.info(f"{'='*80}\n")
    return {
        'lower_grade_contexts': results['lower_grade_contexts'] if results['lower_grade_contexts'] else None,
        'higher_grade_contexts': results['higher_grade_contexts'] if results['higher_grade_contexts'] else None,
        'images': results['images'] if results['images'] else None,
        'videos': results['videos'] if results['videos'] else None
    }

async def query_vdb_nec(index, query, subject, grade, type, embed_model='text-embedding-ada-002', top_k=7):
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

    def query_index(metadata_filter):
        # pc = Pinecone(api_key="dcd21dc3-be0a-44c3-b0ad-73127bb04eb7")
        logger.info(f"\nQuerying index with filter: {metadata_filter}")
        index = pc.Index(index_name)
        # loop = asyncio.get_event_loop()

        res = index.query(vector=embedding, filter=metadata_filter, top_k=top_k, include_metadata=True)
        filtered_matches = list(filter(lambda match: match['score'] > 0.75, res['matches']))
        
        return [{
            'text': match['metadata'].get('text', ''),
            'grade': match['metadata'].get('grade', ''),
            'subject': match['metadata'].get('subject', '')
        } for match in filtered_matches]
    
    # Build lower and higher grade filters using the helper function
    lower_grade_filter, higher_grade_filter = build_filters_nec(subject, grade, type)

    # Define image filter WITH GRADE RESTRICTIONS for NEC
    grade_float = float(grade)
    if subject.lower() == "science":
            image_filter = {
                "subject": {"$eq": "biology image"},
                "grade": {"$lte": 10.0, "$gte": grade_float}  # NEC: Grade 6-10 range
            }
    else:
            image_filter = {
                "subject": {"$eq": subject.lower() + " image"},
                "grade": {"$lte": 10.0, "$gte": grade_float}  # NEC: Grade 6-10 range
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

    logger.info(f"\n{'='*80}")
    logger.info(f"RAG RESULTS FOR SESSION")
    logger.info(f"{'='*80}")
    logger.info(f"Lower Grade Contexts: {results.get('lower_grade_contexts', [])}")
    logger.info(f"Higher Grade Contexts: {results.get('higher_grade_contexts', [])}")
    logger.info(f"Images: {results.get('images', [])}")
    logger.info(f"Videos: {results.get('videos', [])}")
    logger.info(f"{'='*80}\n")

    return {
        'lower_grade_contexts': results['lower_grade_contexts'] if results['lower_grade_contexts'] else None,
        'higher_grade_contexts': results['higher_grade_contexts'] if results['higher_grade_contexts'] else None,
        'images': results['images'] if results['images'] else None
    }



def format_results(vdb_results):
    lower_grade_contexts = vdb_results.get('lower_grade_contexts', [])
    higher_grade_contexts = vdb_results.get('higher_grade_contexts', [])
    images = vdb_results.get('images', [])
    videos = vdb_results.get('videos', [])

    # Ensure lists are not None
    if lower_grade_contexts is None:
        lower_grade_contexts = []
    if higher_grade_contexts is None:
        higher_grade_contexts = []
    if images is None:
        images = []
    if videos is None:  
        videos = []
    # Helper function to combine texts and images for the same grade
    def combine_content(contexts, images, videos): 
        combined = {}
        for context in contexts:
            grade = str(context['grade'])
            if grade not in combined:
                combined[grade] = {'texts': [], 'images': [], 'videos': []} 
            combined[grade]['texts'].append(context['text'])
        
        for image in images:
            grade = str(image.get('grade', ''))
            description = image.get('text', '')
            if grade in combined:
                combined[grade]['images'].append(description)
            else:
                combined[grade] = {'texts': [], 'images': [description], 'videos': []}

        for video in videos:
            grade = str(video.get('grade', ''))
            description = video.get('text', '')
            if grade in combined:
                combined[grade]['videos'].append(description)
            else:
                combined[grade] = {'texts': [], 'images': [], 'videos': [description]}
        
        return combined
    # Format the result
    def format_grade_content(title, combined):
        result = f"{title}:\n\n"
        for grade, content in combined.items():
            result += f"### Grade {grade} ###\n\n"
            result += "Text Chunk:\n\n"
            result += "\n\n".join(content['texts']) + "\n\n"
            if content['images']:
                result += "Images:\n\n"
                result += "\n\n".join(content['images']) + "\n\n"
            else:
                result += "Images:\nThere are no images for this grade.\n\n"

            if content['videos']:
                result += "Videos:\n\n"
                result += "\n\n".join(content['videos']) + "\n\n"
            else:
                result += "Videos:\nThere are no videos for this grade.\n\n"
        return result

    # Combine and format lower grades
    lower_combined = combine_content(lower_grade_contexts, images, videos)
    lower_result = format_grade_content("Lower Grades", lower_combined)

    # Combine and format higher grades 
    higher_combined = combine_content(higher_grade_contexts, images, videos)
    higher_result = format_grade_content("Higher Grades", higher_combined)

    return lower_result, higher_result

async def choose_bucket(query, conversation_history):
    # Prepare the full query with conversation history
    history_text = "\n".join(f"{exchange['role'].title()}: {exchange['content']}" for exchange in conversation_history)



    full_query = f"""

You are an AI assistant tasked with determining whether a student is requesting a response from a higher grade level based on their conversation history and current query. Your goal is to choose the appropriate variable name that holds the context for the response.

First, carefully review the conversation history:
<history>
{history_text}
</history>

Now, consider the user's most recent query:
<query>
{query}
</query>

Analyze the conversation history and the current query to determine if the student is asking for information from a higher grade level. Look for indicators such as:
- Explicit request for more advanced information
- Expressions of wanting to learn more

Based on your analysis, make a decision:
- If you determine that the student is asking for a higher grade response, choose the variable name "higher_result"
- In all other cases, choose the variable name "lower_result"

Provide your decision in the following format:

        ### Answer Style ###

        Your response should follow -\n

        class choose_bucket(BaseModel):
           bucket_name: str - it will be lower_result or higher_result



Remember, the bucket_name should be either "higher_result" or "lower_result" based on your analysis. Do not include any explanations or additional text in your response.

        """

    # Add user query to conversation history only if it is related or there are filtered nodes
    # conversation_history.append({"role": "user", "content": query})
    # logger.info("full query is ", full_query)

    # Sending the query to OpenAI
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[
                {   "role":"system",
                    "content": "You are a helpful assistant. Your response should be in JSON format.",
    
                },
                {
                    "role": "user", 
                    "content": full_query,
                },
            ],
            response_format={"type": "json_object"},
        )

        # Extracting the response
        response = completion.choices[0].message.content

        # # # Update the conversation history with the response
        # conversation_history.append({"role": "assistant", "content": response})

        return response
    except Exception as e:
        logger.error(f"Error in processing query: {e}")
        return "An error occurred while processing the query."
    

async def query_transformation(query, conversation_history):

    # Prepare the full query with conversation history
    history_text = "\n".join(f"{exchange['role'].title()}: {exchange['content']}" for exchange in conversation_history)

    image_names = "\n".join(
    item['content']['image_name']
    for item in conversation_history
    if item['role'] == 'assistant' and isinstance(item['content'], dict) and 'image_name' in item['content']
)
    video_names = "\n".join(
        item['content']['video_name']
        for item in conversation_history
        if item['role'] == 'assistant' and isinstance(item['content'], dict) and 'video_name' in item['content']
    )

    full_query = f"""

        ###Instruction###

        You are a helpful assistant who rewrites the query to eliminate the vagueness. 
        
        When rewriting the query:
        Identify any pronouns or vague references (e.g., "it," "that," "this", "A", "1") and replace them with their specific referents from the conversation history.
        
        
        If rewriting is not needed, you produce the same query.

 
        For instance, if the user says 'tell me more about it,' use the conversation history to determine what 'it' refers to and rewrite the query accordingly.You must not use the used images again

        ###Example###

        Some times, the user is very brief in responses.

        User: Tell me about it?
        User:A
        User:2

        You have judge from the history of the conversation (mostly end of the conversation history to understand) and make it meaningful by adding the right context. You will deal with MCQ options, Match the following etc. 

        Do not do anything else. Never Ever.

        ###Conversation History###
        {history_text}

        ###User Query###
        {query}

        ###Used Images###
        {image_names}

        ###Used Videos###
        {video_names}

        ### Answer Style ###
        Do not write anything else. Just produce the transformed query or original query as you think. It will go into vector database. So make sure you must not write anything else. 
 
        """

    # Add user query to conversation history only if it is related or there are filtered nodes
    # conversation_history.append({"role": "user", "content": query})
    # logger.info("full query is ", full_query)

    # Sending the query to OpenAI
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
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

        # # # Update the conversation history with the response
        # conversation_history.append({"role": "assistant", "content": response})

        return response
    except Exception as e:
        logger.error(f"Error in processing query: {e}")
        return "An error occurred while processing the query."

async def classify_subject(query, subjects_list=None):
    tools = [
        {
            "type": "function",
            "function": {
                "name": "classify_subject",
                "description": "Classify the given query into one of these subjects " + str(subjects_list),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The query or text to be classified based on subjects."
                        },
                        "subject": {
                            "type": "string",
                            "enum": subjects_list + ["General Query"],
                            "description": "The classified subject or General Query if not related to the specific subjects"
                        }
                    },
                    "required": ["subject"]
                }
            }
        }
    ]

    subject_classification = await client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "You are an expert in classifying a query from a student into a respective subject or a General Query. Use General Query only when you are utmost sure that something is not related to subjects,otherwise classify the query into relevant subject. Sometimes a student might suggest, then classify as what student has asked"
            },
            {
                "role": "user",
                "content": f"Classify the subject of this query: {query}"
            }
        ],
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "classify_subject"}}
    )

    result = json.loads(subject_classification.choices[0].message.tool_calls[0].function.arguments)
    return result['subject']

async def classify_subject_nec(query: str, subjects_list=None):
    tools = [
        {
            "type": "function",
            "function": {
                "name": "classify_subject_nec",
                "description": "Classify the given query into one of these subjects",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The query or text to be classified"
                        },
                        "subject": {
                            "type": "string",
                            "enum": subjects_list + ["General Query"],
                            "description": "The classified subject or General Query if not related to the specific subjects"
                        }
                    },
                    "required": ["subject"]
                }
            }
        }
    ]

    subject_classification = await client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "You are an expert in classifying a query from a student into a respective subject or a General Query. Use General Query when you are utmost sure that something is not related to subjects. Sometimes a student might suggest, then classify as what student has asked"
            },
            {
                "role": "user",
                "content": f"Classify the subject of this query: {query}"
            }
        ],
        tools=tools,
        tool_choice={"type": "function", "function": {"name": "classify_subject_nec"}}
    )

    result = json.loads(subject_classification.choices[0].message.tool_calls[0].function.arguments)
    return result['subject']

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
                        {"type": "text", "text": "Describe everything you see in this image. Include objects, text, diagrams, and any details. If there's handwritten or printed text, transcribe it exactly."},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/{image_format};base64,{base64_image}"}}
                    ],
                }
            ],
            max_tokens=300
        )
        logger.info("Image transcription LLM response received for session {session_id}")
        logger.debug("Image transcription response:", response)
        return response.choices[0].message.content
    except Exception as e: 
        logger.error(f"Error during image transcription: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

def get_grade_subject_content(subject, grade, board, type):

    if board in ["CBSE", "PREP"]:
        board = "CBSE"
    elif board in ["SSC-BSET"]:
        board = "SSC-BSET"
    elif board in ["NIOS"]:
        board = "NIOS"
    elif board in ["IGCSE"]:
        board = "IGCSE"
    logging.info(f"Fetching content for Subject: {subject}, Grade: {grade}, Board: {board}")
    
    json_file_paths = {
        "CBSE": {
            "Math": f"/home/ubuntu/main_apis/{type}/cbse/maths.json",
            "Chemistry": f"/home/ubuntu/main_apis/{type}/cbse/chemistry.json",
            "Physics": f"/home/ubuntu/main_apis/{type}/cbse/physics.json",
              "Accountancy": f"/home/ubuntu/main_apis/{type}/cbse/accountancy.json"
        },
        "NEC": {
            "Math": f"/home/ubuntu/main_apis/{type}/nec/math.json"
        },
        "SSC-BSET": {
            "Math": f"/home/ubuntu/main_apis/{type}/bset/math.json",
            "Chemistry": f"/home/ubuntu/main_apis/{type}/bset/chemistry.json",
            "Physics": f"/home/ubuntu/main_apis/{type}/bset/physics.json"
        },
        "IGCSE": {
            "Math": f"/home/ubuntu/main_apis/{type}/igcse/math.json",
            "Physics": f"/home/ubuntu/main_apis/{type}/igcse/physics.json",
            "Chemistry": f"/home/ubuntu/main_apis/{type}/igcse/chemistry.json"
        },
        "NIOS": {
            "Math": f"/home/ubuntu/main_apis/{type}/nios/math.json"
        },
    }
    
    # json_file_paths = {
    #     "CBSE": {
    #         "Math": f"D:\\AI-Scripts-on-Server\\{type}\\cbse\\maths.json",
    #         "Chemistry": f"D:\\AI-Scripts-on-Server\\{type}\\cbse\\chemistry.json",
    #         "Physics": f"D:\\AI-Scripts-on-Server\\{type}\\cbse\\physics.json",
    #         "Accountancy": f"D:\\AI-Scripts-on-Server\\{type}\\cbse\\accountancy.json"
    #     },
    #     "NEC": {
    #         "Math": f"D:\\AI-Scripts-on-Server\\{type}\\nec\\math.json"
    #         # "Science": f"D:\\AI-Scripts-on-Server\\{type}\\nec\\science.json"
    #     },
    #     "SSC-BSET": {
    #         "Math": f"D:\\AI-Scripts-on-Server\\{type}\\bset\\math.json",
    #         "Chemistry": f"D:\\AI-Scripts-on-Server\\{type}\\bset\\chemistry.json",
    #         "Physics": f"D:\\AI-Scripts-on-Server\\{type}\\bset\\physics.json"
    #     },
    #     "IGCSE": {
    #         "Math": f"D:\\AI-Scripts-on-Server\\{type}\\igcse\\math.json",
    #         "Physics": f"D:\\AI-Scripts-on-Server\\igcse\\physics.json",
    #         "Chemistry": f"D:\\AI-Scripts-on-Server\\{type}\\igcse\\chemistry.json"
    #     }
    # }
    board_upper = board.upper()

    board_paths = json_file_paths[board_upper]

    json_file = board_paths.get(subject)

    if not json_file:
        raise ValueError(f"Invalid subject: {subject}")
    
    if not os.path.exists(json_file):
        raise FileNotFoundError(f"JSON file not found: {json_file}")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Filter for the specific grade
    grade_data = None
    for item in data:
        if (item.get("grade") == grade and 
            item.get("subject") == subject.lower() and 
            item.get("board") == board.upper()):
            grade_data = item
            break
    
    if not grade_data:
        raise ValueError(f"No data found for {subject} grade {grade} board {board}")

    return json.dumps(grade_data, indent=2, ensure_ascii=False)



# def get_cached_subject_content(subject, board="CBSE"):
#     cache_file_paths = {
#     "CBSE": {
#          "Math": "/home/ubuntu/main_apis/cbse/maths.txt",
#          "Chemistry": "/home/ubuntu/main_apis/cbse/chemistry.txt",
#          "Physics": "/home/ubuntu/main_apis/cbse/physics.txt"
#      },
#      "NEC": {
#          "Math": "/home/ubuntu/main_apis/nec/maths.txt"
#      }
#  }
    
# # def get_cached_subject_content(subject, board="CBSE"):
# #     cache_file_paths = {
# #    "CBSE": {
# #        "Math": "./cbse/maths.txt",
# #        "Chemistry": "./cbse/chemistry.txt",
# #        "Physics": "./cbse/physics.txt"
# #    },
# #    "NEC": {
# #        "Math": "./nec/maths.txt"
# #    }
# # }

    # if board not in cache_file_paths:
    #     raise ValueError(f"Invalid board: {board}")
        
    # board_paths = cache_file_paths[board]
    # cache_file = board_paths.get(subject)
    
    # if not cache_file:
    #     raise ValueError(f"Invalid subject: {subject} for board: {board}")
    
    # if not os.path.exists(cache_file):
    #     raise FileNotFoundError(f"Cache file not found: {cache_file}")
    
    # with open(cache_file, 'r') as file:
    #     return file.read()

# # Initialize cache for each board and subject
# CACHED_CONTENT = {
#     "CBSE": {
#         "Math": get_cached_subject_content("Math", "CBSE"),
#         "Chemistry": get_cached_subject_content("Chemistry", "CBSE"),
#         "Physics": get_cached_subject_content("Physics", "CBSE")
#     },
#     "NEC": {
#         "Math": get_cached_subject_content("Math", "NEC")
#     }
# }

async def process_subject_query(name, query, grade, board, conversation_history, subject, type, image_data=None, flag_for_name=False, session_id=None, context_manager=None, whatsapp=False):

    history_text = "\n".join(f"{exchange['role'].title()}: {exchange['content']}" for exchange in conversation_history)
    latex_underline = "\\rule{1cm}{0.4pt}"
    #vertexai.init(project="ivory-streamer-473110-e4", location="us-central1")  # update region

    # cached_content = CACHED_CONTENT["CBSE"][subject]

    cached_content = get_grade_subject_content(subject, grade, board, type)
    if not cached_content:
        raise ValueError(f"Invalid subject: {subject}")

    if flag_for_name:
        prompt_for_user_greet = f"""Greet student by {name} to maintain personalization. """
    else:
        prompt_for_user_greet = f"""Don't greet or use name in each response.  """
    # client = genai.Client(
    # vertexai=True,
    # project="ivory-streamer-473110-e4",   # your GCP project ID
    # location="us-central1"                # region where Gemini 2.5 Pro is available
    # )

    # # Define the model
    # model_id = "gemini-2.5-flash"

        # Prompt to send


    # Fetch video context
    formatted_video_context = ""
    video_names = []
    logger.debug("Call before VDB")

    if session_id and context_manager:
        current_context = await query_vdb(query, subject, board, grade, type, embed_model='text-embedding-ada-002', whatsapp=whatsapp)
        videos = current_context.get('videos', [])
        logger.debug("VDB video fetch successful")
        # Track used videos from history
        for item in conversation_history:
            if item['role'] == 'assistant' and isinstance(item['content'], dict):
                if 'video_name' in item['content'] and item['content']['video_name'] != 'NA':
                    video_names.append(item['content']['video_name'])
        
        video_names_str = "\n".join(video_names) if video_names else "None"
        logger.debug("Join of video names complete")
        if videos:
            formatted_video_context = "Available Videos:\n\n"
            for video in videos:
                formatted_video_context += f"Grade {video.get('grade', '')}: {video.get('text', '')}\nVideo: {video.get('video_name', '')}\n\n"
    
    logger.debug("video formatting done, generating prompt")

    if whatsapp:
        full_query = whatsapp_process_subject_query(query, grade, subject, history_text, name, prompt_for_user_greet)
    else:
        full_query = f"""
    Give me a JSON dict. Do not write anything else.

    Do not add any information from your own knowledge. You MUST MUST NOT do it. 

    You are a {subject} teacher helping a student named {name} who is in grade {grade}. Your task is to provide clear, step-by-step explanations for {subject} problems. Use simple language and break down complex concepts into easily understandable parts.
    
    Break response into small paragraphs. Write in a way which can induce readability - Like Headings, Paragraph Change, Bullets - when there are several points, Use of Tables where there is a comparisonetc. Make headings bold.

    {prompt_for_user_greet}

    Whenever you are writing an equation, be careful about subscript and superscript.
          
    Guidelines:
    - Provide step-by-step solutions
    - Use simple language and explain any {subject} terms
    - Encourage the student's efforts and curiosity
    - If the question is unclear, ask for clarification
    - Relate the {subject} concept to real-world applications when possible
    - Also, when the problem/topic is from higher grade then the grade level {grade}, then let the student know that they will learn about it later in their studies. Do NOT mention specific grade numbers or chapter names in your response.
    - Do not provide information from higher grades. You are spoiling the learning experience. Stick to the current grade level {grade} content only.
   
     Previous conversation:
    {history_text}

    Student's question:
    {query}

    Video context:
    {formatted_video_context}
    
    Videos already used:
    {video_names_str}

    Please provide a helpful, encouraging response that addresses the student's {subject} question.

    Also, remember that you dont have the ability to show images for {subject}. Let student know if he asks.

    Response format:
    Always provide your response in below format using the following structure:
    Your entire response must be a valid JSON object. Do not include any text outside of the JSON object.


    You also support LaTeX equations used for academic and technical writing. Your task is to help users write LaTeX equations by providing the appropriate code. YOU MUST MUST DO IT correctly. 

    1. Inline equations: Use single dollar signs ($) to enclose inline equations. These are equations that appear within a line of text.
  

    2. Displayed equations: Use double dollar signs ($$) to enclose displayed equations. These are equations that should appear on their own line, centered.

    3. For fill in the blanks -  always write like this -{latex_underline} - with in latex equations.

    4. When giving real world examples, for money problem use indian rupees.
    
    5. Whenever you refer to dollar amounts (e.g., $6),you must escape the dollar symbol like `\\$` so it renders correctly as currency.

        For example:
        Correct: The item costs \\$6
        Incorrect: The item costs $6


    When writing any content that includes mathematical expressions:

    1. **Mathematical Delimiters**:
    - You must use single `$` for inline mathematics 
    - You must use double `$$` for displayed mathematics (centered on separate line)

    2. **Commands and Symbols**:
    - Every LaTeX command must start with `\\` (backslash)
    - Never show raw command text (like \\alpha) outside math mode
    - Use proper LaTeX notation for all special symbols

    3. **Mixed Content**:
    - When combining text and math in the same expression, wrap text portions in `\\text{{}}`
    - Keep consistent spacing around operators and delimiters
    - Don't break equations across different math environments

    4. **Validation Steps**:
    - Ensure all math expressions are properly delimited
    - Verify all special symbols use LaTeX commands
    - Check for balanced delimiters and proper nesting

    5. **Video Selection**:
    - Pick ONLY ONE video that is most relevant to the current query
    - Do NOT pick videos from the "Videos already used" list
    - If no video is relevant, use "NA"
    - Never include multiple video names separated by commas

When creating mathematical tables with LaTeX equations that require multiple lines in a cell:

1. Use `<br>` between each line of equations
2. Each equation line should be enclosed in $$
3. Format:
   - Enclose each equation in $$
   - Add <br> between lines
   - No spaces before or after <br>
   

   IMPORTANT: Never mention the image_name or video_name value in your response text. Only fill it in the JSON field.

    class ChatbotResponse(BaseModel):
        "response": "your response" 
        "image_name": "NA", 
        "video_name": "Select ONLY ONE most relevant video name from the Videos section, or NA if no video is 
        relevant"
        "self_reflection_tag": "Grade", Grade from which problem is. There can be multiple grades. 
        "is_3D_present": "NA"
        "image_description": "NA"
        "video_description": "NA" 
    """
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"<{subject.lower()}_syllabus>{cached_content}</{subject.lower()}_syllabus>",
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

   # contents = [Part.from_text(full_query)]

    


    if image_data:
        image_format = imghdr.what(None, h=image_data)
        if image_format not in ['jpeg', 'png']:
             raise ValueError("Unsupported image format. Only JPEG and PNG are allowed.")
        
        # base64_image = base64.b64encode(image_data).decode('utf-8')
        # messages[0]["content"].insert(0, {
        #     "type": "image",
        #     "source": {
        #         "type": "base64",
        #         "media_type": f"image/{image_format}",
        #         "data": base64_image,
        #     },
        # })

        # contents.append(
        #     Part.from_data(
        #         mime_type=f"image/{image_format}",
        #         data=image_data
        #     )
        # )
   
    try:
#         logger.debug("Before Gen AI Executor")
#         loop = asyncio.get_event_loop()
#         response = await loop.run_in_executor(ai_executor, lambda: genai_client.models.generate_content(
#     model="gemini-2.5-flash",
#     contents=[
#         str(cached_content),          # plain text, no dict wrapper
#         str(generic_instructions),       # plain text
#         str(full_query)                 # plain text
#     ]
# ))
#         logger.info(f"Gemini completion done")

        
        completion = await claude_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            temperature=0.0,
            messages=messages,
            max_tokens=4096 if not whatsapp else 2048,
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        )

# logger.info default format

        # logger.info(f"Gemini completion: {response.text}")

        #response_escaped = response.text.replace("\\", "\\\\").strip("`").strip()
        # response_escaped = await parse_gemini_json(response.text)
        # response_json = json.loads(
        #     "{" + response_escaped[:response_escaped.rfind("}") + 1], strict=False
        # )
        logging.info(f"Claude completion: {completion}")
        response = completion.content[0].text
        response_escaped = response.replace("\\", "\\\\")
        # response_escaped = re.sub(r"(?<!\\)(\\[()])", r"\\\\\1", response)

        try:
            response_json = json.loads("{" + response_escaped[:response_escaped.rfind("}") + 1], strict=False)
        except json.JSONDecodeError:
            logging.warning("Claude: JSON parsing failed, calling repair LLM...")
            repaired_json = await repair_json_with_llm(f"Fix this JSON and give me correct JSON: {response}")
            logging.info(f"repaired_json: {repaired_json}")
            response_json = json.loads(repaired_json, strict=False)
        # response_json = json.loads(response)

        logger.info(f"\n{'='*80}")
        logger.info(f"JSON RESPONSE FROM LLM")
        logger.info(f"{'='*80}")
        logger.info(f"Response: {response_json.get('response', '')}")
        logger.info(f"Image Name: {response_json.get('image_name', 'NA')}")
        logger.info(f"Video Name: {response_json.get('video_name', 'NA')}")
        logger.info(f"Self Reflection Tag: {response_json.get('self_reflection_tag', '')}")
        logger.info(f"{'='*80}\n")

        return response_json


    except Exception as e:
        logger.error(f"Error in processing {subject} query: {e}")
        return json.dumps({"error": str(e)})


##### With claude validation #####
# def process_subject_query(name, query, grade, conversation_history, subject, image_data=None, flag_for_name=False):
#     history_text = "\n".join(f"{exchange['role'].title()}: {exchange['content']}" for exchange in conversation_history)
#     latex_underline = "\\rule{1cm}{0.4pt}"
#     # vertexai.init(project="ivory-streamer-473110-e4", location="us-central1")  # update region

#     cached_content = CACHED_CONTENT["CBSE"][subject]

#     cached_content = get_grade_subject_content(subject, grade)

#     if not cached_content:
#         raise ValueError(f"Invalid subject: {subject}")

#     if flag_for_name:
#         prompt_for_user_greet = f"""Greet student by {name} to maintain personalization. """
#     else:
#         prompt_for_user_greet = f"""Don't greet or use name in each response.  """
#     # client = genai.Client(
#     # vertexai=True,
#     # project="ivory-streamer-473110-e4",   # your GCP project ID
#     # location="us-central1"                # region where Gemini 2.5 Pro is available
#     # )

#     ## Define the model
#     # model_id = "gemini-2.5-flash"

#         # Prompt to send
#     full_query = f"""
#     Give me a JSON dict. Do not write anything else.

#     Do not add any information from your own knowledge. You MUST MUST NOT do it. 

#     You are a {subject} teacher helping a student named {name} who is in grade {grade}. Your task is to provide clear, step-by-step explanations for {subject} problems. Use simple language and break down complex concepts into easily understandable parts.
    
#     Break response into small paragraphs. Write in a way which can induce readability - Like Headings, Paragraph Change, Bullets - when there are several points, Use of Tables where there is a comparisonetc. Make headings bold.

#     {prompt_for_user_greet}

#     Whenever you are writing an equation, be careful about subscript and superscript.
          
#     Guidelines:
#     - Provide step-by-step solutions
#     - Use simple language and explain any {subject} terms
#     - Encourage the student's efforts and curiosity
#     - If the question is unclear, ask for clarification
#     - Relate the {subject} concept to real-world applications when possible
#     - Also, when the problem/topic is from higher grade, then student know that they will learn about it later in their studies. Do NOT mention specific grade numbers or chapter names in your response.

#     Previous conversation:
#     {history_text}

#     Student's question:
#     {query}

#     Response format:
#     Always provide your response in below format using the following structure:
#     Your entire response must be a valid JSON object. Do not include any text outside of the JSON object.


#     You also support LaTeX equations used for academic and technical writing. Your task is to help users write LaTeX equations by providing the appropriate code. YOU MUST MUST DO IT correctly. 

#     1. Inline equations: Use single dollar signs ($) to enclose inline equations. These are equations that appear within a line of text.
  

#     2. Displayed equations: Use double dollar signs ($$) to enclose displayed equations. These are equations that should appear on their own line, centered.

#     3. For fill in the blanks -  always write like this -{latex_underline} - with in latex equations.

#     4. When giving real world examples, for money problem use indian rupees.
    
#     5. Whenever you refer to dollar amounts (e.g., $6),you must escape the dollar symbol like `\\$` so it renders correctly as currency.

#         For example:
#         Correct: The item costs \\$6
#         Incorrect: The item costs $6


#     When writing any content that includes mathematical expressions:

#     1. **Mathematical Delimiters**:
#     - You must use single `$` for inline mathematics 
#     - You must use double `$$` for displayed mathematics (centered on separate line)

#     2. **Commands and Symbols**:
#     - Every LaTeX command must start with `\\` (backslash)
#     - Never show raw command text (like \\alpha) outside math mode
#     - Use proper LaTeX notation for all special symbols

#     3. **Mixed Content**:
#     - When combining text and math in the same expression, wrap text portions in `\\text{{}}`
#     - Keep consistent spacing around operators and delimiters
#     - Don't break equations across different math environments

#     4. **Validation Steps**:
#     - Ensure all math expressions are properly delimited
#     - Verify all special symbols use LaTeX commands
#     - Check for balanced delimiters and proper nesting

# When creating mathematical tables with LaTeX equations that require multiple lines in a cell:

# 1. Use `<br>` between each line of equations
# 2. Each equation line should be enclosed in $$
# 3. Format:
#    - Enclose each equation in $$
#    - Add <br> between lines
#    - No spaces before or after <br>
   

#    IMPORTANT: Never mention the image_name or video_name value in your response text. Only fill it in the JSON field.

#     class ChatbotResponse(BaseModel):
#         "response": "your response" 
#         "image_name": "NA", 
#         "video_name": "NA"
#         "self_reflection_tag": "Grade", Grade from which problem is. There can be multiple grades. 
#         "is_3D_present": "NA"
#         "image_description": "NA"
#         "video_description": "NA"

#     Please provide a helpful, encouraging response that addresses the student's {subject} question.

#     Also, remember that you dont have the ability to show images for {subject}. Let student know if he asks.
#     """

#     messages = [
#         {
#             "role": "user",
#             "content": [
#                 {
#                     "type": "text",
#                     "text": f"<{subject.lower()}_syllabus>{cached_content}</{subject.lower()}_syllabus>",
#                     "cache_control": {"type": "ephemeral"}
#                 },
#                 {
#                     "type": "text",
#                     "text": full_query
#                 }
#             ]
#         },
#         {
#             "role": "assistant",
#             "content": [
#                 {
#                     "type": "text",
#                     "text": "Here is the JSON requested:\n{"
#                 }
#             ]
#         }
#     ]

#     if image_data:
#         image_format = imghdr.what(None, h=image_data)
#         if image_format not in ['jpeg', 'png']:
#              raise ValueError("Unsupported image format. Only JPEG and PNG are allowed.")
        
#         base64_image = base64.b64encode(image_data).decode('utf-8')
#         messages[0]["content"].insert(0, {
#             "type": "image",
#             "source": {
#                 "type": "base64",
#                 "media_type": f"image/{image_format}",
#                 "data": base64_image,
#             },
#         })

#     try:
#         # CLAUDE API CALL
#         completion = claude_client.messages.create(
#             model="claude-sonnet-4-5-20250929",
#             temperature=0.0,
#             messages=messages,
#             max_tokens=4096,
#             extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
#         )
#         logger.info(f"Claude completion: {completion}")
#         response = completion.content[0].text
#         logger.info(response)

#         response_escaped = response.replace("\\", "\\\\")
#         response_json = json.loads("{" + response_escaped[:response_escaped.rfind("}") + 1], strict=False)

#         return response_json

#     except Exception as e:
#         logger.error(f"Error in processing {subject} query: {e}")
#         return json.dumps({"error": str(e)})


# async def parse_gemini_json(text: str):
#     """
#     Cleans Gemini output and parses it into a Python dict safely.
#     Handles ```json fences, stray text, and malformed backslashes.
#     """
#     # Remove code fences like ```json ... ```
#     cleaned = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.IGNORECASE)
#     cleaned = re.sub(r"```$", "", cleaned.strip())

#     # Ensure only JSON part is extracted
#     match = re.search(r"\{.*\}", cleaned, re.DOTALL)
#     if not match:
#         raise ValueError("No JSON object found in Gemini output")

#     json_candidate = match.group(0)

#     try:
#         return json.loads(json_candidate)   # strict parse
#     except json.JSONDecodeError:
#         # fallback: escape backslashes and try again
#         safe_candidate = json_candidate.replace("\\", "\\\\")
#         return json.loads(safe_candidate)

parse_executor = ThreadPoolExecutor(max_workers=4)


# def clean_and_parse_json(text: str) -> dict:
#     """
#     Cleans Gemini output and parses it into a Python dict safely.
#     Handles code fences, stray text, trailing commas, and minor JSON issues.
#     """
#     # Remove code fences like ```json ... ```
#     cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE).strip()

#     # Extract the JSON object
#     match = re.search(r"\{.*\}", cleaned, re.DOTALL)
#     if not match:
#         return {"error": "No JSON object found", "raw": text}

#     json_candidate = match.group(0)

#     # Fix common JSON issues
#     # 1. Remove trailing commas
#     json_candidate = re.sub(r",\s*}", "}", json_candidate)
#     json_candidate = re.sub(r",\s*\]", "]", json_candidate)

#     # 2. Optional: add commas between string-number / string-string pairs
#     # This is a naive fix; can be improved for complex cases
#     json_candidate = re.sub(r'"\s*"([a-zA-Z_]+)"', r'", "\1"', json_candidate)

#     try:
#         return json.loads(json_candidate)
#     except json.JSONDecodeError as e:
#         return {"error": str(e), "raw": json_candidate}


VALID_JSON_ESCAPES = set('"\\/bfnrtu')

VALID_JSON_ESCAPES = set('"\\/bfnrtu')

def extract_json_block(text: str) -> str:
    """Extract the largest JSON object from text."""
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in LLM output")
    return match.group(0)

def escape_invalid_backslashes(s: str) -> str:
    """Escape invalid JSON backslashes (e.g., in LaTeX) without touching valid escapes."""
    result = []
    i = 0
    while i < len(s):
        if s[i] == "\\":
            if i + 1 < len(s) and s[i + 1] in VALID_JSON_ESCAPES:
                result.append(s[i:i+2])
                i += 2
            else:
                result.append("\\\\")
                i += 1
        else:
            result.append(s[i])
            i += 1
    return "".join(result)

def normalize_json(text: str) -> str:
    """Fix trailing commas and escape invalid backslashes."""
    text = re.sub(r",\s*([}\]])", r"\1", text)
    text = escape_invalid_backslashes(text)
    return text

def format_latex_for_frontend(text: str) -> str:
    """
    Convert LLM-style \$…\$ into $$…$$ for frontend rendering.
    Preserves other LaTeX commands (\frac, \times, etc.).
    """
    # Inline math: \$…\$ → $$…$$
    text = re.sub(r"\\\$(.+?)\\\$", r"$$\1$$", text)
    # Optional: convert \( … \) → $ … $
    text = re.sub(r"\\\\\((.+?)\\\\\)", r"$\1$", text)
    return text

def parse_and_format_llm_json(text: str) -> Dict[str, Any]:
    """
    Full pipeline:
    1. Extract JSON from LLM text
    2. Normalize invalid JSON
    3. Parse into Python dict
    4. Format LaTeX for frontend rendering
    """
    try:
        # Step 1 + 2: Extract and normalize
        json_block = extract_json_block(text)
        normalized = normalize_json(json_block)

        # Step 3: Parse JSON
        parsed = json.loads(normalized)

        # Step 4: Format LaTeX fields
        for key in ["response", "textAnswer"]:
            if key in parsed and isinstance(parsed[key], str):
                parsed[key] = format_latex_for_frontend(parsed[key])

        return parsed
    
    except Exception as e:
        # Return error + raw for debugging
        return {"error": str(e), "raw": text}



async def parse_gemini_json(text: str) -> dict:
    """
    Async wrapper to prevent blocking event loop for large Gemini outputs.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(parse_executor, parse_and_format_llm_json, text)



async def process_nec_math_query(name, query, grade, conversation_history, board, subject, type, image_data=None, whatsapp=False):
    history_text = "\n".join(f"{exchange['role'].title()}: {exchange['content']}" for exchange in conversation_history)
    logger.debug("history for pcm function is", history_text)

    # cached_content = CACHED_CONTENT["NEC"]["Math"]

    cached_content = get_grade_subject_content("Math", grade, board, type)

    if not cached_content:
        raise ValueError(f"Invalid subject: {subject}")

    if whatsapp:
        full_query = whatsapp_process_nec_math_query(query, grade, subject, history_text, name)
    else:
        full_query = f"""
    Give me a JSON dict. Do not write anything else.

    Do not use textbook word in your responses. Instead use curriculum word in your responses. 

    You are a {subject} teacher helping a student named {name} who is in grade {grade}. Your task is to provide clear, step-by-step explanations for {subject} problems. Use simple language and break down complex concepts into easily understandable parts.
    
    Break response into small paragraphs. Write in a way which can induce readability - Like Headings, Paragraph Change, Bullets - when there are several points, Use of Tables where there is a comparisonetc. Make headings bold.

    
    Whenever you are writing an equation, be careful about subscript and superscript.

    You can use the name to greet the student when name is present. It is a way to maintain personalization. Don't use it in each response. Use it in the following situations:
    1. At the beginning of the conversation to greet the student.
    2. When the student seems discouraged or frustrated, to offer personalized encouragement.
    3. When praising the student for asking a good question or showing understanding.
    4. When transitioning to a new topic or subtopic within the subject.
    5. At the end of the conversation, to say goodbye.

    Guidelines:
    - Provide step-by-step solutions
    - Use simple language and explain any {subject} terms
    - Encourage the student's efforts and curiosity
    - If the question is unclear, ask for clarification
    - Relate the {subject} concept to real-world applications when possible
    - Also, when the problem/topic is from higher grade, then student know that they will learn about it later in their studies. Do NOT mention specific grade numbers or chapter names in your response.

    Previous conversation:
    {history_text}

    Student's question:
    {query}

    Response format:
    Always provide your response in below format using the following structure:
    Your entire response must be a valid JSON object. Do not include any text outside of the JSON object.


    You also support LaTeX equations used for academic and technical writing. Your task is to help users write LaTeX equations by providing the appropriate code. YOU MUST MUST DO IT correctly. 

    1. Inline equations: Use single dollar signs ($) to enclose inline equations. These are equations that appear within a line of text.
  

    2. Displayed equations: Use double dollar signs ($$) to enclose displayed equations. These are equations that should appear on their own line, centered.

    3. For fill in the blanks -  always write like this - \\_\\_\\_ - with in latex equations.

    When writing any content that includes mathematical expressions:

    1. **Mathematical Delimiters**:
    - Use single `$` for inline mathematics 
    - Use double `$$` for displayed mathematics (centered on separate line)

    2. **Commands and Symbols**:
    - Every LaTeX command must start with `\\` (backslash)
    - Never show raw command text (like \\alpha) outside math mode
    - Use proper LaTeX notation for all special symbols

    3. **Mixed Content**:
    - When combining text and math in the same expression, wrap text portions in `\\text{{}}`
    - Keep consistent spacing around operators and delimiters
    - Don't break equations across different math environments

    4. **Validation Steps**:
    - Ensure all math expressions are properly delimited
    - Verify all special symbols use LaTeX commands
    - Check for balanced delimiters and proper nesting

When creating mathematical tables with LaTeX equations that require multiple lines in a cell:

1. Use `<br>` between each line of equations
2. Each equation line should be enclosed in $$
3. Format:
   - Enclose each equation in $$
   - Add <br> between lines
   - No spaces before or after <br>

    class ChatbotResponse(BaseModel):
        "response": "your response" 
        "image_name": "NA", 
        "self_reflection_tag": "Grade", Grade from which problem is. There can be multiple grades. 
        "is_3D_present": "NA"
        "image_description": "NA"

    Please provide a helpful, encouraging response that addresses the student's {subject} question.

    Also, remember that you dont have the ability to show images for {subject}. Let student know if he asks.
    """

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"<{subject.lower()}_syllabus>{cached_content}</{subject.lower()}_syllabus>",
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
            max_tokens=4096 if not whatsapp else 2048,
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"}
        )
        logger.info(f"Claude completion: {completion}")
        response = completion.content[0].text

        response_escaped = response.replace("\\", "\\\\")
        # response_escaped = re.sub(r"(?<!\\)(\\[()])", r"\\\\\1", response)

        try:
            response_json = json.loads("{" + response_escaped[:response_escaped.rfind("}") + 1], strict=False)
        except json.JSONDecodeError:
            logging.warning("Claude: JSON parsing failed, calling repair LLM...")
            repaired_json = await repair_json_with_llm(f"Fix this JSON and give me correct JSON: {response}")
            logging.info(f"repaired_json: {repaired_json}")
            response_json = json.loads(repaired_json, strict=False)
        # response_json = json.loads(response)

        logger.info(f"\n{'='*80}")
        logger.info(f"JSON RESPONSE FROM LLM")
        logger.info(f"{'='*80}")
        logger.info(f"Response: {response_json.get('response', '')}")
        logger.info(f"Image Name: {response_json.get('image_name', 'NA')}")
        logger.info(f"Self Reflection Tag: {response_json.get('self_reflection_tag', '')}")
        logger.info(f"{'='*80}\n")

        return response_json

    except Exception as e:
        logger.error(f"Error in processing {subject} query: {e}")
        return json.dumps({"error": str(e)})

# Define the main chatbot function
async def process_nec_science(name, query, grade, conversation_history, session_id, context_manager, subject, type, image_data=None, whatsapp=False):
    """
    Chatbot function that uses query results as context for the query.
    
    :param query: User's query.
    :param grade: Student's grade.
    :param conversation_history: The history of the conversation.
    :param session_id: Unique session identifier.
    :param context_manager: Context manager for handling session contexts.
    :return: The response from the chatbot.
    """
    # logger.info("query is", query)
    # query_for_vdb = query_transformation(query, conversation_history)
    # logger.info("trasnformed query is", query)
    # subject = classify_subject(query_for_vdb)
    # logger.info("classified subject is", subject)

    # if subject == "Math":
    #     return process_math_query(name, query, grade, conversation_history)
    
  
    
    formatted_context = ""
    context_note = ""
    higher_grade_note = ""

    if subject != "General Query":
        current_context = await query_vdb_nec(index, query, subject, grade, type, embed_model='text-embedding-ada-002')
        # logger.info(current_context)
        
        lower_grade_contexts = current_context['lower_grade_contexts']
        higher_grade_contexts = current_context['higher_grade_contexts']

        if not lower_grade_contexts and not higher_grade_contexts:
            context_note = "There is no context available for this query. The assistant should not answer from its own knowledge."
        elif not lower_grade_contexts and higher_grade_contexts:
            context_note = "There is no context from the student's grade or below, but higher grade information is available."
            higher_grade_note = "Ask the student if they want an answer based on higher grade information."
        elif lower_grade_contexts and higher_grade_contexts:
            context_note = "Context from the student's grade or below is available. Higher grade information is also available."
            higher_grade_note = "If the lower grade context is insufficient to answer the query comprehensively, ask the student if they want additional information from a higher grade."
        elif lower_grade_contexts and not higher_grade_contexts:
            context_note = "Only context from the student's grade or below is available."

        lower_result, higher_result = format_results(current_context)
        formatted_context = lower_result + "\n\n" + higher_grade_note + "\n\n" + higher_result

        logger.debug(formatted_context)
        context_manager.set_context(session_id, formatted_context)
    else:
        context_note = "This is a general query. No specific subject context is available. See if the question is relevent to the grade {grade} level in Indian CBSE context. You must must not answer from your knowledge. When you tell to students, always say - from your text book instead of context"

    history_text = "\n".join(f"{exchange['role'].title()}: {exchange['content']}" for exchange in conversation_history)
    logger.debug("history for chatbot function is", history_text)

    if whatsapp:
        full_query = whatsapp_process_nec_science(query, grade, subject, context_note, formatted_context, history_text, name)
    else:
        full_query = f"""

Give me a JSON dict. Do not write anything else.

You are a teacher helping students who are not native English speakers. Your task is to rewrite a given text using the simplest words possible, so it's easy for these students to understand.

Break response into small paragraphs. Write in a way which can induce readability - Like Headings, Paragraph Change, Bullets - when there are several points, Use of Tables where there is a comparisonetc. Make headings bold.

When there is a students response asking for an image - If you dont have one, let them know. You must not avoid the question. 

Here are some guidelines to follow:
- Use short, common words
- Avoid idioms or complex phrases
- Use simple sentence structures
- Break long sentences into shorter ones
- Explain difficult concepts in basic terms

The name of the student is {name}. If name is not present, dont greet by name. Dont say noone etc. 

When name is present, You can use the name to greet the student. It is a way to maintain personalization. Don't use it in each response. Use it in the following situations:
1. At the beginning of the conversation to greet the student.
2. When the student seems discouraged or frustrated, to offer personalized encouragement.
3. When praising the student for asking a good question or showing understanding.
4. When transitioning to a new topic or subtopic within the subject.
5. At the end of the conversation, to say goodbye.

Maintain empathy in serious topics. Guidelines for maintaining empathy:
1. Acknowledge the emotions and experiences of those affected
2. Use a respectful and caring tone
3. Avoid minimizing or dismissing the seriousness of the situation
4. Be patient and understanding
5. Offer support or resources when appropriate, but don't force solutions
6. Use inclusive language that doesn't alienate or stereotype

For image_name - Always pick images from the context note. Think carefully - You can make a mistake. If there is a valid image then only write the image_description.

You are a teacher who breaks an answer in small paragraphs for students in grade {grade}.
Your task is to provide informative and engaging responses to student queries while adhering to specific guidelines and ONLY ONLY utilizing provided context. You must not use your own knowledge.
You are honest.
Tell upfront that you cannot answer non subject query (or a general query) - as students sometimes try to divert you. Be strict and brief, dont answer from your knowledge.
You also have a capability to show an image to student. You do it by picking an image name in image_name key. You dont need to tell student the name etc. Your responses are consumed by front end.

You are empathetic to students weaknesses, problems. Dont ask them to study when they are in trouble, be brief, Listen and ask if they need help in subject. 

For normal queries where they are not sad:
You acknowledge what they have asked by being enthusiastic - dont be repetitive in your style,  and also can try to amaze a student with some fact (whenever available dont push too much), intresting story and then answer it as based on Context from the book. Try to give some activity when only relevant (dont push) 
You response structure can be made of small paragraphs mixed with Bold Words as headings and or some form of information in table structure. You need to think which is the best way and which combination will work best.


Use tables to struture+

You should structure your answer in table when you show a difference between two or multiple things or you want to summarise multiple things about a topic

Keep the generic greetings short and sweet when student says Hi or Hello. Answer briefly when query is almost same as previous query. Let them know that you have exhausted the context from book in a creative way.

Input variables:
<subject>{subject}</subject>
<grade>{grade}</grade>
Context from Book
<context_note>{context_note}</context_note>
<formatted_context>{formatted_context}</formatted_context>
Context from Book
<history_text>{history_text}</history_text>
<query>{query} - Put in small paragraphs</query>



Response format:
Use clear and simple English words appropriate for the student's grade level.
Always provide your response in below format using the following structure:
Your entire response must be a valid JSON object. Do not include any text outside of the JSON object.

    You also support LaTeX equations used for academic and technical writing. Your task is to help users write LaTeX equations by providing the appropriate code. YOU MUST MUST DO IT correctly. 

    1. Inline equations: Use single dollar signs ($) to enclose inline equations. These are equations that appear within a line of text.
  

    2. Displayed equations: Use double dollar signs ($$) to enclose displayed equations. These are equations that should appear on their own line, centered.

    3. For fill in the blanks -  always write like this - \\_\\_\\_ - with in latex equations.
     
 When writing any content that includes mathematical expressions:

    1. **Mathematical Delimiters**:
    - Use single `$` for inline mathematics 
    - Use double `$$` for displayed mathematics (centered on separate line)

    2. **Commands and Symbols**:
    - Every LaTeX command must start with `\\` (backslash)
    - Never show raw command text (like \\alpha) outside math mode
    - Use proper LaTeX notation for all special symbols

    3. **Mixed Content**:
    - When combining text and math in the same expression, wrap text portions in `\\text{{}}`
    - Keep consistent spacing around operators and delimiters
    - Don't break equations across different math environments

    4. **Validation Steps**:
    - Ensure all math expressions are properly delimited
    - Verify all special symbols use LaTeX commands
    - Check for balanced delimiters and proper nesting

When creating mathematical tables with LaTeX equations that require multiple lines in a cell:

1. Use `<br>` between each line of equations
2. Each equation line should be enclosed in $$
3. Format:
   - Enclose each equation in $$
   - Add <br> between lines
   - No spaces before or after <br>

class ChatbotResponse(BaseModel):
    "response": "your response" 
    "image_name": "Image name or NA", 
    "self_reflection_tag": "Yes - Grade(s)" or "No" or "General Query",
    "is_3D_present": "Yes" or "No" or "NA"
    "image_description": "image description from Image subheading in Context from book - describing what an image is and  how it is related to response. Sometimes an image description is about a chart too. Modify your desscription based on it"

Sample Response:

"response": "The history of the Roman Empire is marked by the rise and fall of one of the most powerful civilizations in human history.\n\nFrom its founding in 27 BC by Augustus to its decline in 476 AD, the Roman Empire left a lasting legacy on law, politics, architecture, and culture.",
"image_name": "G8_HIS_C07_S3.1_Fig_3.4_roman_empire_map", 
"self_reflection_tag": "Yes - Grade8,9",
"is_3D_present": "No"
"image_description": "image description from Image subheading in Context from book - describing what an image is and  how it is related to response" - Always start with a sentence like The below image illustrates, depicts or any creative way.

Personality and tone:
- Act as an enthusiastic and creative teacher, focusing strictly on {subject}.
- Steer non-{subject} queries towards {subject} in an engaging way. Dont add information - be brief.
- Maintain a supportive and encouraging tone throughout the interaction.

Guidelines:
Use clear and simple English words appropriate for the student's grade level.

Keep the generic greetings short and sweet.

You will have Context from Book. Under which text and images are segregated based on Grades.

Subheading are Text Chunks and Images for Each Grade

Pick a grade from which query can be answered. Pick an image from same grade if it complements. Do not pick loosely related image.

If the grade from which query has been answered is higher than student grade, tell that student will learn more about in higher grade.

Add description about image from Image heading - The description should be telling what the image is and how is it related to main part of the answer. 

Use only the context from book for answer. Do not use your knowledge.


Self Reflection Tag - CRITICAL INSTRUCTIONS:
- Use "Yes - Grade(s)" ONLY when you actually provide content from those grades to the student
- Use "No" when you refuse to provide content (e.g., "you will learn this in higher grades")
- Use "General Query" for non-subject questions
- The tag reflects what grade content is ACTUALLY given in your response, not what grade the topic belongs to

Always steer non subject query towards subject.

When you ask a question based on student query, you should not pick an image.

You should not be repetitive in picking an image. Example you picked an image, student again asked a question for which same image is valid, you should put NA as image.

Break your answer in small paragraphs.

The length of answer can be around 100 to 125 words.

When a student ask a question, give them a question which can enhance learning.

When a question from the student is not clear, ask them to give clarity.

Also, dont give reference to the images, tables and headings etc from the text chunks in context from the book heading. We dont want them to feel that they are reading their book.

Also, when a student asks about you - tell them you are here to help them explore and Seek answers, discover new knowledge, broaden your understanding, re-imagine
your lessons and make learning fun through stories, interactive activities,
mnemonics, and projects! - Dont tell anything else about yourself and how you work.

When a query is about an image direcly - Like Show me an image etc. Dont write the same content in reponse and image description key. It looks boring and repetitive. It is acceptable to keep the response short then.

Also, produce an image in image_name when you talk about an image. Sometimes, you miss. Thats Bad!!!




"""

    # Add user query to conversation history only if it is related or there are filtered nodes
    # conversation_history.append({"role": "user", "content": query})
    # logger.info("full query is ", full_query)

    # Sending the query to OpenAI
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
            max_tokens=4096 if not whatsapp else 2048,
        )
        logger.info(f"Claude completion: {completion}")
        response = completion.content[0].text

        response_escaped = response.replace("\\", "\\\\")
        # response_escaped = re.sub(r"(?<!\\)(\\[()])", r"\\\\\1", response)

        try:
            response_json = json.loads("{" + response_escaped[:response_escaped.rfind("}") + 1], strict=False)
        except json.JSONDecodeError:
            logging.warning("Claude: JSON parsing failed, calling repair LLM...")
            repaired_json = await repair_json_with_llm(f"Fix this JSON and give me correct JSON: {response}")
            logging.info(f"repaired_json: {repaired_json}")
            response_json = json.loads(repaired_json, strict=False)
        # response_json = json.loads(response)

        return response_json

    except Exception as e:
        logger.error(f"Error in processing {subject} query: {e}")
        return json.dumps({"error": str(e)})


async def chatbot_with_context_nec(name, query, grade, conversation_history, session_id, context_manager, subject, board, type, whatsapp=False):
    """
    Chatbot function that uses query results as context for the query.
    
    :param query: User's query.
    :param grade: Student's grade.
    :param conversation_history: The history of the conversation.
    :param session_id: Unique session identifier.
    :param context_manager: Context manager for handling session contexts.
    :return: The response from the chatbot.
    """
    # logger.info("query is", query)
    # query_for_vdb = query_transformation(query, conversation_history)
    # logger.info("trasnformed query is", query)
    # subject = classify_subject(query_for_vdb)
    # logger.info("classified subject is", subject)

    # if subject == "Math":
    #     return process_math_query(name, query, grade, conversation_history)

    
    formatted_context = ""
    context_note = ""
    higher_grade_note = ""

    if subject != "General Query":
        current_context =  await query_vdb_nec(index, query, subject, grade, type, embed_model='text-embedding-ada-002')
        # logger.info(current_context)
        
        lower_grade_contexts = current_context['lower_grade_contexts']
        higher_grade_contexts = current_context['higher_grade_contexts']

        if not lower_grade_contexts and not higher_grade_contexts:
            context_note = "There is no context available for this query. The assistant should not answer from its own knowledge."
        elif not lower_grade_contexts and higher_grade_contexts:
            context_note = "There is no context from the student's grade or below, but higher grade information is available."
            higher_grade_note = "Ask the student if they want an answer based on higher grade information."
        elif lower_grade_contexts and higher_grade_contexts:
            context_note = "Context from the student's grade or below is available. Higher grade information is also available."
            higher_grade_note = "If the lower grade context is insufficient to answer the query comprehensively, ask the student if they want additional information from a higher grade."
        elif lower_grade_contexts and not higher_grade_contexts:
            context_note = "Only context from the student's grade or below is available."

        lower_result, higher_result = format_results(current_context)
        formatted_context = lower_result + "\n\n" + higher_grade_note + "\n\n" + higher_result

        logger.debug(formatted_context)

        # logger.info(formatted_context)
        context_manager.set_context(session_id, formatted_context)
    else:
        context_note = "This is a general query. No specific subject context is available. See if it can be answered from context available to you. You must must not answer from your knowledge. When you tell to students, always say - from your text book instead of context"

    history_text = "\n".join(f"{exchange['role'].title()}: {exchange['content']}" for exchange in conversation_history)
    logger.debug("history for chatbot function is", history_text)

    if whatsapp:
        full_query = whatsapp_chatbot_with_context_nec(query, grade, subject, context_note, formatted_context, history_text, name)
    else:
        full_query = f"""

    Do not use textbook word in your responses. Instead use curriculum word in your responses. 

    Two things will define you:
    One is answering only using the context from the book. You MUST MUST MUST NOT add any information from your own knowledge.
    Two is when student is asking you a general query or non subject ones - divert them to studies. You MUST MUST MUST NOT add any information from your own knowledge. Be brief.

    Humanty education is your responsibility - You will kill thousands if you do not follow. 

Break the answer in small paragraphs. For comparison of two or multiple entities use Tables format to produce the answer.

When it is a general query or non subject related - divert student back to studies. You MUST NOT ANSWER it from your own knowledge. You have a tendency to add some information 

You are an AI teacher designed to assist non-native English-speaking students in understanding {subject} concepts. Your primary goal is to provide clear, simplified explanations while maintaining an engaging and supportive tone.

First, let's review the context and information provided for this interaction:

Subject: 
<subject>{subject}</subject>

Student's grade level:
<grade>{grade}</grade>

Instructions about the context from the book:
<context_note>{context_note}</context_note>

Context from the book:
<book_context>{formatted_context}</book_context>

Coversation history for the session:
<conversation_history>{history_text}</conversation_history>

Now, here's the student's query:
<query>{query}</query>


### Response Planning

Before responding, please analyze the query and plan your response:

1. Determine if the query is related to {subject}. If not, plan a brief, polite redirection to the subject.
2. Identify if the relevant and enough information (from the book context) to frame an answer is present.
3. Consider the context from the students grade level for the response. If it is not possible - Let student know that they wil learn about it in higher grade.
4. Plan the structure of your response (paragraphs, headings, bullets, tables). Tables shall be used in comparisons of two or multiple things.
5. Decide if an image would be helpful and relevant.
6. Simplify complex terms or concepts that may need simplification for non-native English speakers.
7. Brainstorm engaging elements to include (interesting facts, activities, etc.).
8. Plan any engaging elements to include (interesting facts, activities, etc.).

### Formulating Response

Instructions for formulating your response:

0. Acknowledge student by {name} to maintain personalization but do not use name in each response.

1. Language and Structure:
- Use simple, common words and avoid idioms or complex phrases.
- Break your response into short paragraphs (3-4 sentences each).
- Use bold headings, bullet points when appropriate. Use tables when you have to do the comparison of multiple things.

2. Content:
- Only use information from the provided context. Do not add external knowledge.
- If the appropriate information is from a higher grade level, mention that the student will learn more about it later in their studies. Do NOT mention specific grade numbers or chapter names.

3. Engagement:
- Maintain an enthusiastic and supportive tone.
- Include an interesting fact or brief activity when relevant.
- Ask a follow-up question to enhance learning.

4. Images:
- If using an image to complement the answer, select one from the same grade level as the content of your response. If it is not possible - Let student know that image is complex for their level and has been shown for reference. They will learn about it in higher grades.
- Do not refer to images, tables, or headings from the context directly.
- Avoid repetitive image usage in consecutive answers.

5. Handling Non-Subject Queries:
- Politely redirect the student to {subject}-related topics.
- Keep these redirections brief and YOU MUST NOT add unrelated information.

6. Empathy:
- Acknowledge emotions and experiences when discussing serious topics.
- Use a respectful and caring tone.
- Offer support or resources when appropriate.

7. Self-Introduction:
- If asked about yourself, say: "I'm here to help you explore and seek answers, discover new knowledge, broaden your understanding, re-imagine your lessons, and make learning fun through stories, interactive activities, mnemonics, and projects!"

8. Response Format

You also support LaTeX equations used for academic and technical writing. Your task is to help users write LaTeX equations by providing the appropriate code. YOU MUST MUST DO IT correctly. 

1. Inline equations: Use single dollar signs ($) to enclose inline equations. These are equations that appear within a line of text.


2. Displayed equations: Use double dollar signs ($$) to enclose displayed equations. These are equations that should appear on their own line, centered.

3. For fill in the blanks -  always write like this - \\_\\_\\_ - with in latex equations.

 When writing any content that includes mathematical expressions:

    1. **Mathematical Delimiters**:
    - Use single `$` for inline mathematics 
    - Use double `$$` for displayed mathematics (centered on separate line)

    2. **Commands and Symbols**:
    - Every LaTeX command must start with `\\` (backslash)
    - Never show raw command text (like \\alpha) outside math mode
    - Use proper LaTeX notation for all special symbols

    3. **Mixed Content**:
    - When combining text and math in the same expression, wrap text portions in `\\text{{}}`
    - Keep consistent spacing around operators and delimiters
    - Don't break equations across different math environments

    4. **Validation Steps**:
    - Ensure all math expressions are properly delimited
    - Verify all special symbols use LaTeX commands
    - Check for balanced delimiters and proper nesting

When creating mathematical tables with LaTeX equations that require multiple lines in a cell:

1. Use `<br>` between each line of equations
2. Each equation line should be enclosed in $$
3. Format:
   - Enclose each equation in $$
   - Add <br> between lines
   - No spaces before or after <br>

class ChatbotResponse(BaseModel):
    "response": "Your explanation here" 
    "image_name": "Relevant image name or NA", 
    "self_reflection_tag": "Yes - Grade(s)" or "No" or "General Query",
    "is_3D_present": "Yes" or "No" or "NA"
    "image_description": "image description from Image subheading in Context from book - describing what an image is and  how it is related to response. Sometimes an image description is about a chart too. Modify your description based on it"

Self Reflection Tag - CRITICAL INSTRUCTIONS:
- Use "Yes - Grade(s)" ONLY when you actually provide content from those grades to the student
- Use "No" when you refuse to provide content (e.g., "you will learn this in higher grades")
- Use "General Query" for non-subject questions
- The tag reflects what grade content is ACTUALLY given in your response, not what grade the topic belongs to


Please provide your response in the following JSON format:


"response": "Your explanation here",
"image_name": "Relevant image name or NA",
"self_reflection_tag": "Yes - Grade(s)" or "No" or "General Query",
"is_3D_present": "Yes" or "No" or "NA",
"image_description": "Brief description of the image and its relevance to the response"


The image_name would look like this - G8_HIS_C07_S3.1_Fig_3.4 (Example) - Make sure to pick the correct image without skipping or adding any characters. They are to be consumed by other applications. 

The description of the image or 3D interactive start with - The below image or 3D interactive illustrates, depicts etc. Be creative in writing. Do not be monotonous.


Remember to use the simplest words possible and maintain an encouraging tone throughout your response.




"""

    # Add user query to conversation history only if it is related or there are filtered nodes
    # conversation_history.append({"role": "user", "content": query})
    # logger.info("full query is ", full_query)

    # Sending the query to OpenAI
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            temperature=0.2,
            max_tokens=4096 if not whatsapp else 2048,
            messages=[
                {   "role":"system",
                    "content": "You are a helpful assistant. Your response should be in JSON format.",
    
                },
                {
                    "role": "user",
                    "content": full_query,
                },
            ],
            response_format={"type": "json_object"},
            # stream=True

        )

        # Extracting the response
        # full_response = ""
        # for chunk in completion:
        #     if chunk.choices[0].delta.content is not None:
        #         content = chunk.choices[0].delta.content
        #         full_response += content
        #         yield content

        response = completion.choices[0].message.content
        response_escaped = response.replace("\\", "\\\\")

        # Parse the full response as JSON
        try:
            response_json = json.loads(response_escaped, strict = False)
        except json.JSONDecodeError:
            logging.warning("Gemini: JSON parsing failed, calling repair LLM...")
            repaired_json = await repair_json_with_llm(f"Fix this JSON and give me correct JSON: {response}")
            logging.info(f"repaired_json: {repaired_json}")
            response_json = json.loads(repaired_json, strict=False)
        
        logger.debug("response is", response_json)
        await add_to_conversation(session_id, "assistant", response_json)
        return response_json

    except Exception as e:
        logger.error(f"Error in processing query: {e}")
        return json.dumps({"error": str(e)})


# Define the main chatbot function
async def chatbot_with_context(name, query, grade, conversation_history, session_id, context_manager, board, subject, type, flag_for_name=False, whatsapp=False):
    """
    Chatbot function that uses query results as context for the query.
    
    :param query: User's query.
    :param grade: Student's grade.
    :param conversation_history: The history of the conversation.
    :param session_id: Unique session identifier.
    :param context_manager: Context manager for handling session contexts.
    :return: The response from the chatbot.
    """
    # logger.info("query is", query)
    # query_for_vdb = query_transformation(query, conversation_history)
    # logger.info("trasnformed query is", query)
    # subject = classify_subject(query_for_vdb)
    # logger.info("classified subject is", subject)

    # if subject == "Math":
    #     return process_math_query(name, query, grade, conversation_history)

  
    
    formatted_context = ""
    context_note = ""
    higher_grade_note = ""

    if subject != "General Query":
        current_context = await query_vdb(query, subject, board, grade, type, embed_model='text-embedding-ada-002', whatsapp=whatsapp)
        lower_grade_contexts = current_context['lower_grade_contexts']
        higher_grade_contexts = current_context['higher_grade_contexts']

        if not lower_grade_contexts and not higher_grade_contexts:
            context_note = "There is no context available for this query. The assistant should not answer from its own knowledge."
        elif not lower_grade_contexts and higher_grade_contexts:
            context_note = "There is no context from the student's grade or below, but higher grade information is available."
            higher_grade_note = "Ask the student if they want an answer based on higher grade information."
        elif lower_grade_contexts and higher_grade_contexts:
            context_note = "Context from the student's grade or below is available. Higher grade information is also available."
            higher_grade_note = "If the lower grade context is insufficient to answer the query comprehensively, ask the student if they want additional information from a higher grade."
        elif lower_grade_contexts and not higher_grade_contexts:
            context_note = "Only context from the student's grade or below is available."

        lower_result, higher_result = format_results(current_context)
        formatted_context = lower_result + "\n\n" + higher_grade_note + "\n\n" + higher_result

        # logger.info(formatted_context)
        context_manager.set_context(session_id, formatted_context)
    else:
        context_note = "This is a general query. No specific subject context is available. See if the question is relevent to the grade {grade} level in Indian CBSE context. You must must not answer from your knowledge. When you tell to students, always say - from your text book instead of context"

    history_text = "\n".join(f"{exchange['role'].title()}: {exchange['content']}" for exchange in conversation_history)
    logger.debug("history for chatbot function is", history_text)

    
#     image_names = "\n".join(
#     item['content']['image_name']
#     for item in conversation_history
#     if item['role'] == 'assistant' and isinstance(item['content'], dict) and 'image_name' in item['content']
# )
#     video_names = "\n".join(
#         item['content']['video_name']
#         for item in conversation_history
#         if item['role'] == 'assistant' and isinstance(item['content'], dict) and 'video_name' in item['content']
#     )
    image_names = []
    video_names = []
    
    
    for item in conversation_history:
        if item['role'] == 'assistant' and isinstance(item['content'], dict):
            if 'image_name' in item['content'] and item['content']['image_name'] != 'NA':
                image_names.append(item['content']['image_name'])
            if 'video_name' in item['content'] and item['content']['video_name'] != 'NA':
                video_names.append(item['content']['video_name'])
    
    image_names_str = "\n".join(image_names) if image_names else "None"
    video_names_str = "\n".join(video_names) if video_names else "None"

    full_query_general = f"""You are an AI teacher designed to assist non-native English-speaking students of grade {grade} in understanding CBSE concepts.
    Student {name} has asked a general query: {query}. When it is a general query - politely divert student back to studies. You MUST NOT ANSWER it from your own knowledge. 
    """
    if whatsapp:
        full_query = whatsapp_chatbot_with_context(query, grade, subject, context_note, formatted_context, history_text, name, board)
    else:
        full_query = f"""

Break the answer in small paragraphs. For comparison of two or multiple entities use Tables format to produce the answer.

When it is a general query - divert student back to studies. You MUST NOT ANSWER it from your own knowledge. 

You are an AI teacher designed to assist non-native English-speaking students of grade {grade} in understanding {subject} concepts. Your primary goal is to provide clear, simplified explanations while maintaining an engaging and supportive tone.

First, let's review the context and information provided for this interaction:

Subject: 
<subject>{subject}</subject>

Student's grade level:
<grade>{grade}</grade>

Instructions about the context from the book:
<context_note>{context_note}</context_note>

Context from the book:
<book_context>{formatted_context}</book_context>

Coversation history for the session:
<conversation_history>{history_text}</conversation_history>

Now, here's the student's query:
<query>{query}</query>

Images used for the session:
<image_names>{image_names_str}<image_names>

Videos used for the session:
<video_names>{video_names_str}</video_names>

### Response Planning

Before responding, please analyze the query and plan your response:

1. Determine if the query is related to {subject}. If not, plan a brief, polite redirection to the subject.
2. Identify if the relevant and enough information (from the book context) to frame an answer is present.
3. Consider the context from the students grade level for the response. If it is not possible - Let student know that they will learn about it later in their studies. Do not give higher grade information if it is not present in the context. Do NOT mention specific grade numbers or chapter names.
4. Plan the structure of your response (paragraphs, headings, bullets, tables). Tables shall be used in comparisons of two or multiple things.
5. Decide if an image would be helpful and relevant. Only if the description of the image is relevant to the query, use image. Do not change the description of the image.
6. Simplify complex terms or concepts that may need simplification for non-native English speakers.
7. Brainstorm engaging elements to include (interesting facts, activities, etc.).
8. Plan any engaging elements to include (interesting facts, activities, etc.).
9. Do not give information that is irrelevant to the grade of the student. You are spoiling the student if you do so.

### Formulating Response

Instructions for formulating your response:

0. Greet student by {name} to maintain personalization only when the {flag_for_name} is True otherwise dont say hello

1. Language and Structure:
- Use simple, common words and avoid idioms or complex phrases.
- Break your response into short paragraphs (3-4 sentences each).
- Use bold headings, bullet points when appropriate. Use tables when you have to do the comparison of multiple things.

2. Content:
- Only use information from the provided context. Do not add external knowledge.
- If the appropriate information is from a higher grade level, mention that the student will learn more about it later in their studies. Do NOT mention specific grade numbers or chapter names.

3. Engagement:
- Maintain an enthusiastic and supportive tone.
- Include an interesting fact or brief activity when relevant.
- Ask a follow-up question to enhance learning.

4. Images:
- If using an image to complement the answer, select one from the same grade level as the content of your response. If it is not possible - Let student know that image is complex for their level and has been shown for reference. They will learn about it in higher grades.
- Do not refer to images, tables, or headings from the context directly.
- Do not use image if the description of the image is not relevant to the query. For example, if the query is about chola kingdom and image description is about Mauryan empire, then do not use image. 
- Avoid repetitive image usage in consecutive answers.

5. Videos:
- If using a video to complement the answer, select one from the same grade level as the content of your response.
- Do not refer to videos, tables, or headings from the context directly.
- Do not use video if the description is not relevant to the query.
- Avoid repetitive video usage in consecutive answers.

6. Handling Non-Subject Queries:
- Politely redirect the student to {subject}-related topics.
- Keep these redirections brief and YOU MUST NOT add unrelated information.
- Do not give response from your own knowledge. Politely redirect them to studies.

7. Empathy:
- Acknowledge emotions and experiences when discussing serious topics.
- Use a respectful and caring tone.
- Offer support or resources when appropriate.

8. Self-Introduction:
- If asked about yourself, say: "I'm here to help you explore and seek answers, discover new knowledge, broaden your understanding, re-imagine your lessons, and make learning fun through stories, interactive activities, mnemonics, and projects!"

9. Response Format

You also support LaTeX equations used for academic and technical writing. Your task is to help users write LaTeX equations by providing the appropriate code. YOU MUST MUST DO IT correctly. 

1. Inline equations: Use single dollar signs ($) to enclose inline equations. These are equations that appear within a line of text.


2. Displayed equations: Use double dollar signs ($$) to enclose displayed equations. These are equations that should appear on their own line, centered.

3. For fill in the blanks -  always write like this - \\_\\_\\_ - with in latex equations.

 When writing any content that includes mathematical expressions:

    1. **Mathematical Delimiters**:
    - Use single `$` for inline mathematics 
    - Use double `$$` for displayed mathematics (centered on separate line)

    2. **Commands and Symbols**:
    - Every LaTeX command must start with `\\` (backslash)
    - Never show raw command text (like \\alpha) outside math mode
    - Use proper LaTeX notation for all special symbols

    3. **Mixed Content**:
    - When combining text and math in the same expression, wrap text portions in `\\text{{}}`
    - Keep consistent spacing around operators and delimiters
    - Don't break equations across different math environments

    4. **Validation Steps**:
    - Ensure all math expressions are properly delimited
    - Verify all special symbols use LaTeX commands
    - Check for balanced delimiters and proper nesting

When creating mathematical tables with LaTeX equations that require multiple lines in a cell:

1. Use `<br>` between each line of equations
2. Each equation line should be enclosed in $$
3. Format:
   - Enclose each equation in $$
   - Add <br> between lines
   - No spaces before or after <br>

IMPORTANT: Never mention the image_name or video_name values in your response text. Only fill them in the JSON fields.

class ChatbotResponse(BaseModel):
    "response": "Your explanation here" 
    "image_name": "Relevant image name or NA", 
    "video_name": "Relevant video name or NA"
    "self_reflection_tag": "Yes - Grade(s)" or "No" or "General Query",
    "is_3D_present": "Yes" or "No" or "NA"
    "image_description": "image description from Image subheading in Context from book"
    "video_description": "video description from Videos subheading in Context from book"

Self Reflection Tag - CRITICAL INSTRUCTIONS:
- Use "Yes - Grade(s)" ONLY when you actually provide content from those grades to the student
- Use "No" when you refuse to provide content (e.g., "you will learn this in higher grades")
- Use "General Query" for non-subject questions
- The tag reflects what grade content is ACTUALLY given in your response, not what grade the topic belongs to


Please provide your response in the following JSON format:


"response": "Your explanation here",
"image_name": "Relevant image name or NA",
"video_name": "Relevant video name or NA",
"self_reflection_tag": "Yes - Grade(s)" or "No" or "General Query",
"is_3D_present": "Yes" or "No" or "NA",
"image_description": "Brief description of the image and its relevance to the response"
"video_description": "Brief description of the video and its relevance to the response"

Do not pick the images from this list {image_names_str}

Do not pick the videos from this list {video_names_str}

The image_name would look like this - G8_HIS_C07_S3.1_Fig_3.4 (Example) - Make sure to pick the correct image without skipping or adding any characters. They are to be consumed by other applications. 

The description of the image or 3D interactive start with - The below image or 3D interactive illustrates, depicts etc. Be creative in writing. Do not be monotonous.


Remember to use the simplest words possible and maintain an encouraging tone throughout your response.




"""

    # Add user query to conversation history only if it is related or there are filtered nodes
    # conversation_history.append({"role": "user", "content": query})
    # logger.info("full query is ", full_query)

    # Sending the query to OpenAI
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            temperature=0.2,
            messages=[
                {   "role":"system",
                    "content": "You are a helpful assistant. Your response should be in JSON format.",
    
                },
                {
                    "role": "user",
                    "content": full_query,
                },
            ],
            response_format={"type": "json_object"},
        )

        response = completion.choices[0].message.content
        logger.debug(f"Raw OpenAI response: {response}")
        
        # Try parsing without modification first
        try:
            response_json = json.loads(response, strict=False)
        except json.JSONDecodeError:
            # If that fails, escape backslashes
            try:
                response_escaped = response.replace("\\", "\\\\")
                response_json = json.loads(response_escaped, strict=False)
            except json.JSONDecodeError:
                logging.warning("Gemini: JSON parsing failed, calling repair LLM...")
                repaired_json = await repair_json_with_llm(f"Fix this JSON and give me correct JSON: {response}")
                logging.info(f"repaired_json: {repaired_json}")
                response_json = json.loads(repaired_json, strict=False)
        
        logger.debug("Parsed response:", response_json)

        logger.info(f"\n{'='*80}")
        logger.info(f"JSON RESPONSE FROM LLM")
        logger.info(f"{'='*80}")
        logger.info(f"Response: {response_json.get('response', '')}")
        logger.info(f"Image Name: {response_json.get('image_name', 'NA')}")
        logger.info(f"Video Name: {response_json.get('video_name', 'NA')}")
        logger.info(f"Self Reflection Tag: {response_json.get('self_reflection_tag', '')}")
        logger.info(f"{'='*80}\n")

        await add_to_conversation(session_id, "assistant", response_json)
        return response_json

    except Exception as e:
        logger.error(f"Error in processing query: {e}")
        return json.dumps({"error": str(e)})




async def chatbot_for_general(name, query, grade, board, conversation_history, session_id, context_manager, subject, flag_for_name=False, whatsapp=False):
    """
    Chatbot function that uses query results as context for the query.
    
    :param query: User's query.
    :param grade: Student's grade.
    :param conversation_history: The history of the conversation.
    :param session_id: Unique session identifier.
    :param context_manager: Context manager for handling session contexts.
    :return: The response from the chatbot.
    """
    # logger.info("query is", query)
    # query_for_vdb = query_transformation(query, conversation_history)
    # logger.info("trasnformed query is", query)
    # subject = classify_subject(query_for_vdb)
    # logger.info("classified subject is", subject)

    # if subject == "Math":
    #     return process_math_query(name, query, grade, conversation_history)


    full_query_general = f"""You are an AI teacher designed to assist non-native English-speaking students of grade {grade} in understanding {board} concepts.
    Student {name} has asked a general query: {query}. When it is a general query - divert student back to studies. You MUST NOT ANSWER it from your own knowledge. 
    
    Please provide your response in the following JSON format:


"response": "Your explanation here",
"image_name": "NA",
"video_name": "NA",
"self_reflection_tag": ""General Query",
"is_3D_present": "NA",
"image_description": "NA"
"video_description": "NA"
    """
    
   
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[
                {   "role":"system",
                    "content": "You are a helpful assistant. Your response should be in JSON format.",
    
                },
                {
                    "role": "user",
                    "content": full_query_general,
                },
            ],
            response_format={"type": "json_object"},
        )

        response = completion.choices[0].message.content
        logger.debug(f"Raw OpenAI response: {response}")
        
        # Try parsing without modification first
        try:
            response_json = json.loads(response, strict=False)
        except json.JSONDecodeError:
            # If that fails, escape backslashes
            try:
                response_escaped = response.replace("\\", "\\\\")
                response_json = json.loads(response_escaped, strict=False)
            except json.JSONDecodeError:
                logging.warning("Gemini: JSON parsing failed, calling repair LLM...")
                repaired_json = await repair_json_with_llm(f"Fix this JSON and give me correct JSON: {response}")
                logging.info(f"repaired_json: {repaired_json}")
                response_json = json.loads(repaired_json, strict=False)
        
        logger.debug("Parsed response:", response_json)
        await add_to_conversation(session_id, "assistant", response_json)
        return response_json

    except Exception as e:
        logger.error(f"Error in processing query: {e}")
        return json.dumps({"error": str(e)})

async def repair_json_with_llm(fix_prompt):
    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-2024-08-06",
            temperature=0.2,
            messages=[
                {   "role":"system",
                    "content": "You are a helpful assistant. Your response should be in JSON format.",
                     },
                {
                    "role": "user",
                    "content": fix_prompt,
                },
            ],
            response_format={"type": "json_object"},
        )
        response = completion.choices[0].message.content
        logger.debug(f"Raw OpenAI response: {response}")
        return response
    except Exception as repair_error:
        logging.error(f"Repair JSON LLM error: {repair_error}")
        return "{}"



# # Conversation Management
# conversation_histories = defaultdict(list)

async def add_to_conversation(session_id, role, content):
    # conversation_histories[session_id].append({"role": role, "content": content})
    collection.update_one(
        {"session_id": session_id},
        {
            "$push": {"messages": {"role": role, "content": content}},
            "$setOnInsert": {"created_at": datetime.utcnow()}
        },
        upsert=True
    )
async def get_conversation(session_id):
    # return conversation_histories[session_id]
    result = collection.find_one({"session_id": session_id})
    if result and "messages" in result:
        return result["messages"]
    return []

async def query_rag_bio(session_id, user_query, subject, grade):
    await add_to_conversation(session_id, "user", user_query)
    # logger.info(conversations)
    conversation_history = await get_conversation(session_id)

    # Get response from chatbot
    response_text = await chatbot_with_context(user_query, conversation_history, subject, grade)
    # logger.info("response text is", response_text)
    await add_to_conversation(session_id, "assistant", response_text)
    # logger.info("Last part", conversations)
    
    return response_text


# # API Models
# class QueryRequest(BaseModel):
#     session_id: str
#     query: str
#     subject: str = Field(..., example="biology")
#     grade: int = Field(..., example=9)

class QueryRequest(BaseModel):
    session_id: str = Form(...)
    query: Optional[str] = Form(None)
    image: Optional[UploadFile] = File(None)
    subject: str = Form(...)
    grade: int = Form(...)
    name: Optional[str] = Form(None) 
    type: str = Form(...)  
    # type: str = Form(default="Book_2019")

class QueryResponse(BaseModel):
    session_id: str
    response: str
    subject: str
    grade: int
    image_name: Optional[str] = None
    video_name: Optional[str] = None
    image_description: Optional[str] = None
    video_description: Optional[str] = None
    self_reflection_tag: Optional[str] = None
    is_3D_present: Optional[str] = None
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


@app.post("/api3/query_endpoint/")
async def process_query(
    session_id: str = Form(...), 
    query: Optional[str] = Form(None), 
    image: Optional[UploadFile] = File(None),
    grade: int = Form(...),
    name: Optional[str] = Form(None),
    board: str = Form(...),
    type: str = Form(...),
    # type: str = Form(default="Book_2019"),
    whatsapp: bool = Form(False)
    ):
    start_time = datetime.now()  
    logger.info(f"Session Id is {session_id} Datetime in function {start_time}")
    if not session_id: 
        raise HTTPException(status_code=400, detail="Session ID is required.")
    if not query and not image:
        raise HTTPException(status_code=400, detail="Either query or image is required.")
    try:
        image_data = None
        image_transcription = ""
        final_query = query  # Store the original or modified query
        
        # Handle image if present
        if image:
            image_data = await image.read()
            image_transcription = await transcribe_image_to_text(image_data)
            
        # Combine query and image transcription if both exist
        if query and image_transcription:
            final_query = f"user query is:{query}.\n User has also uploaded an image. Image transcription is:{image_transcription}"
            await add_to_conversation(session_id, "user", final_query)
        elif query:
            await add_to_conversation(session_id, "user", query)
        elif image_transcription:
            final_query = f"User has uploaded an image as a query. Image transcription is:{image_transcription}"
            await add_to_conversation(session_id, "user", final_query)
            
        conversation_history = await get_conversation(session_id)
        
        for item in conversation_history:
            if item['role'] == 'assistant':
                flag_for_name = False
                break
            else:
                flag_for_name = True

        loop = asyncio.get_event_loop()
        subjects_task = loop.run_in_executor(executor, get_subjects_for_board_grade, board, grade, type)
        
        query_for_vdb = await query_transformation(final_query, conversation_history)

        subjects_list = await subjects_task
        logger.info(f"Loaded subjects for {board} Grade {grade}: {subjects_list}")


        # Classify subject based on board
        if board.upper() == "NEC":
            subject = await classify_subject_nec(query_for_vdb, subjects_list)
            
            if subject == "Math":
                response = await process_nec_math_query(
                    name=name,
                    query=query_for_vdb,
                    grade=grade,
                    conversation_history=conversation_history,
                    subject=subject,
                    board=board,
                    type=type,
                    image_data=image_data,
                    whatsapp=whatsapp
                )
            else:  # Science, History, Geography, Civics, General Query
                response = await chatbot_with_context_nec(
                    name=name,
                    query=query_for_vdb,
                    grade=grade,
                    conversation_history=conversation_history,
                    session_id=session_id,
                    context_manager=session_context_manager,
                    subject=subject,
                    board=board,
                    type=type,
                    whatsapp=whatsapp
                )
        elif board.upper() == "CBSE" or board.upper() == "PREP" or board.upper() == "SSC-BSET" or board.upper() == "IGCSE" or board.upper() == "NIOS":
            subject = await classify_subject(query_for_vdb, subjects_list)
            logger.info(f"CBSE subject classified as: {subject}")
            
            if subject in ["Math", "Chemistry", "Physics", "Accountancy"]:
                response = await process_subject_query(
                    name=name,
                    query=query_for_vdb,
                    grade=grade,
                    conversation_history=conversation_history,
                    subject=subject,
                    type=type,
                    image_data=image_data,
                    flag_for_name=flag_for_name,
                    session_id=session_id,
                    context_manager=session_context_manager,
                    board=board,
                    whatsapp=whatsapp
                )
            elif subject in ["General Query"]:
                response = await chatbot_for_general(
                    name=name,
                    query=query_for_vdb,
                    grade=grade,
                    board=board,
                    conversation_history=conversation_history,
                    session_id=session_id,
                    context_manager=session_context_manager,
                    subject=subject,
                    flag_for_name = flag_for_name,
                    whatsapp=whatsapp
                )
            else:
                response = await chatbot_with_context(
                    name=name,
                    query=query_for_vdb,
                    grade=grade,
                    board=board,
                    conversation_history=conversation_history,
                    session_id=session_id,
                    context_manager=session_context_manager,
                    subject=subject,
                    type=type,
                    flag_for_name = flag_for_name,
                    whatsapp=whatsapp
                )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported board: {board}") 
        completed_time = datetime.now()
        logger.info(f"Session Id {session_id} completed at {completed_time}, Duration: {completed_time - start_time}")  
        return JSONResponse(content=response)
    except Exception as e:
        logger.error(f"Error in processing query for Session ID {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api3/reset_conversation/")
async def reset_conversation(session_id: str = Form(...)):
    session_context_manager.clear_context(session_id)
    # conversation_histories[session_id].clear()
    collection.delete_one({"session_id": session_id})
    return {"message": f"Context and conversation history cleared for session {session_id}"}
    
async def generate_title(conversation_history):
    # Extract only the user's questions
    user_questions = " ".join([exchange['content'] for exchange in conversation_history if exchange['role'] == 'user'])

    # Create a prompt for OpenAI
    prompt = f'''Generate a short concise title (maximum five words) to store the conversation history based on these questions. Use the most important idea of the conversation and make sure it is within the key ideas. You could modify the presentation as you like. Do not include title in quotes\n

        ###User Questions###
         
         \n{user_questions}'''

    try:
        completion = await client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Your response should be a short title.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error in generating title: {e}")
        return "Error in title generation"

@app.post("/api3/generate_title/")
async def generate_title_endpoint(session_id: str = Form(...)):
    # if session_id not in conversation_histories:
    conversation_exists = collection.find_one({"session_id": session_id})
    if not conversation_exists:
        raise HTTPException(status_code=404, detail="Session ID not found")

    try:
        conversation_history = await get_conversation(session_id)
        title = await generate_title(conversation_history)
        return {"title": title}
    except Exception as e:
        logger.error(f"Error in generating title for Session ID {session_id}: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while generating the title")
