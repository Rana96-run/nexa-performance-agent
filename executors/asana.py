import asana
from config import ASANA_TOKEN, ASANA_PROJECTS


def get_client():
    configuration = asana.Configuration()
    configuration.access_token = ASANA_TOKEN
    return asana.ApiClient(configuration)


def create_task(title: str, description: str, project_key: str, task_type: str = "Recommendation"):
    """
    Create an Asana task in the correct project.
    project_key: 'daily_activity' | 'optimization' | 'campaigns_hub' | 'seasonal'
    """
    client = get_client()
    tasks_api = asana.TasksApi(client)

    project_id = ASANA_PROJECTS.get(project_key)
    if not project_id:
        print(f"Unknown project key: {project_key}")
        return None

    task_body = {
        "data": {
            "name": f"[{task_type}] {title}",
            "notes": description,
            "projects": [project_id],
        }
    }

    try:
        task = tasks_api.create_task(task_body, {})
        return task["gid"]
    except asana.ApiException as e:
        print(f"Asana error: {e}")
        return None
