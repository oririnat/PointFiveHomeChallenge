
import sys
sys.path.insert(0, '../services_utils')
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, or_
from typing import List
from config import GITHUB_AUTH_TOKEN
from db import SessionLocal, engine
import concurrent.futures
import models
import schemas
import requests
import os

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="GitHub Events API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Angular app origin
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Fetch star count from GitHub API
def get_repo_star_count(repo_name: str) -> int:
    url = f"https://api.github.com/repos/{repo_name}"
    headers = {}
    if GITHUB_AUTH_TOKEN:
        headers['Authorization'] = f"token {GITHUB_AUTH_TOKEN}"
    try: 
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get("stargazers_count", 0)
        else:
            return 0
    except Exception as e:
        print(f"Error fetching star count for repo {repo_name}: {e}")
        return 0


@app.get("/events/", response_model=List[schemas.EventSchema])
def list_events(
    skip: int = 0,
    limit: int = 20,
    search_term: str = '',
    db: Session = Depends(get_db)
):
    # Base query with eager loading for Actor and Repository relationships
    query = db.query(models.Event).options(
        joinedload(models.Event.actor),
        joinedload(models.Event.repository)
    )

    # Apply search filter if a search_term is provided
    if search_term:
        query = query.filter(
            or_(
                models.Event.actor.has(login=search_term),       # Search in actor's login (name)
                models.Event.repository.has(name=search_term),   # Search in repository name
                models.Event.type.ilike(f"%{search_term}%")      # Search in event type (case-insensitive)
            )
        )

    # Apply ordering, pagination, and execute the query
    events_with_actors_and_repos = (
        query
        .order_by(desc(models.Event.id))
        .offset(skip)
        .limit(limit)
        .all()
    )

    # Map each repository name to its Repository object, only for repositories missing star counts
    repo_map = {
        event.repository.name: event.repository
        for event in events_with_actors_and_repos
        if event.repository.stars is None
    }

    # Fetch star counts concurrently for each unique repository
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(get_repo_star_count, repo_name): repo_name
            for repo_name in repo_map.keys()
        }

        for future in concurrent.futures.as_completed(futures):
            repo_name = futures[future]
            try:
                repo_map[repo_name].stars = future.result()  # Update the stars count for the repository
            except Exception as e:
                print(f"Error fetching star count for repo {repo_name}: {e}")

    # Save the stars count to the database
    db.commit()

    return events_with_actors_and_repos

@app.get("/events/count")
def count_events(db: Session = Depends(get_db)):
    count = db.query(models.Event).count()
    return {"total_events": count}

@app.get("/actors/recent", response_model=List[schemas.ActorSchema])
def list_recent_actors(db: Session = Depends(get_db)):
    subquery = db.query(
        models.Event.actor_id,
        models.Event.created_at
    ).order_by(models.Event.created_at.desc()).distinct(models.Event.actor_id).limit(20).subquery()

    actors = db.query(models.Actor).join(
        subquery, models.Actor.id == subquery.c.actor_id
    ).order_by(subquery.c.created_at.desc()).all()

    return actors


@app.get("/repositories/recent", response_model=List[schemas.RepositorySchema])
def list_recent_repositories(db: Session = Depends(get_db)):
    # Subquery to get the 20 most recent repositories involved in events
    subquery = db.query(
        models.Event.repo_id,
        models.Event.created_at
    ).order_by(models.Event.created_at.desc()).distinct(models.Event.repo_id).limit(20).subquery()

    # Main query to fetch repositories
    repositories = db.query(models.Repository).join(
        subquery, models.Repository.id == subquery.c.repo_id
    ).order_by(subquery.c.created_at.desc()).all()

    # Map each repository name to its Repository object, only if star count is missing
    repo_map = {
        repo.name: repo for repo in repositories if repo.stars is None
    }

    # Fetch star counts concurrently for each unique repository
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(get_repo_star_count, repo_name): repo_name
            for repo_name in repo_map.keys()
        }

        for future in concurrent.futures.as_completed(futures):
            repo_name = futures[future]
            try:
                # Update the stars count for the repository in repo_map
                repo_map[repo_name].stars = future.result()
            except Exception as e:
                print(f"Error fetching star count for repo {repo_name}: {e}")

    # Commit updated star counts to the database
    db.commit()

    return repositories