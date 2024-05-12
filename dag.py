from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import logging
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load(data):
    if data:
        df = pd.DataFrame(data)
        df.to_csv('/mnt/c/Users/7410/Documents/airflow/dags/data/dawn.csv', index=False)
    else:
        logging.info("No data to save.")

def ET(url, source, selector):
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504, 524])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))

    try:
        response = session.get(url, timeout=20)
        soup = BeautifulSoup(response.text, 'html.parser')
        links = [a['href'] for a in soup.select(selector) if 'href' in a.attrs]
        links = [url + '/' + link.lstrip('/') if not link.startswith('http') else link for link in links]

        data = []
        for link in links:
            try:
                response = session.get(link, timeout=20)
                article_soup = BeautifulSoup(response.text, 'html.parser')
                title_element = article_soup.find('title')
                title = title_element.text.strip() if title_element else None
                paragraphs = article_soup.find_all('p')
                description = ' '.join(p.text.strip() for p in paragraphs if p.text.strip()) if paragraphs else None

                if title and description:
                    title = re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', title)).strip()
                    description = re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', description)).strip()
                    data.append({
                        'title': title,
                        'description': description,
                        'source': source,
                        'url': link
                    })
            except requests.exceptions.RequestException as e:
                logging.error(f"Failed to fetch details from {link}: {str(e)}")

        return data
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch {url}: {str(e)}")
        return []

dag = DAG('dawn_pipeline', default_args={'owner': 'airflow', 'retries': 1},
          start_date=datetime(2024, 5, 10), schedule_interval="@daily")

with dag:
    source = 'Dawn'
    info = {'url': 'https://www.dawn.com', 'selector': 'article.story a.story__link'}

    git_dvc_init = BashOperator(
        task_id='git_dvc_init',
        bash_command="cd /mnt/c/Users/7410/Documents/airflow/dags && git init && dvc init && git remote add origin https://github.com/umammahh/MLOPS-Assignment02.git && dvc remote add -d myremote gdrive://11-QMrqlVisVaQUKPpJ1QetDcZjrR1NOl"
    )  
    extract_trans = PythonOperator(
        task_id='extract_transform',
        python_callable=ET,
        op_kwargs={'url': info['url'], 'source': source, 'selector': info['selector']}
    )
    loading = PythonOperator(
        task_id='load',
        python_callable=load,
        op_args=[extract_trans.output],
    )
    dvc_git_push = BashOperator(
        task_id='dvc_and_git_push',
        bash_command="cd /mnt/c/Users/7410/Documents/airflow/dags && dvc add data/dawn.csv && dvc push && git add data/dawn.csv.dvc data/.gitignore && git commit -m 'Updated files' && git push origin master"
    )

    git_dvc_init >> extract_trans >> loading >> dvc_git_push
