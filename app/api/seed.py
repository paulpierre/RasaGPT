'''
seed.py users the models in model.py and populates the database with dummy content
'''

# ----------------
# Database imports
# ----------------
from helpers import (
    create_org_by_org_or_uuid,
    create_project_by_org,
    create_document_by_file_path
)
from config import (
    FILE_UPLOAD_PATH,
    logger
)
from util import (
    get_file_hash
)
import os

# --------------------
# Create organizations
# --------------------

organizations = [
    {
        'display_name': 'Pepe Corp.',
        'namespace': 'pepe',
        'projects': [
            {
                'display_name': 'Pepetamine',
                'docs': [
                    'project-pepetamine.md'
                ]
            },
            {
                'display_name': 'Frogonil',
                'docs': [
                    'project-frogonil.md'
                ]
            },
            {
                'display_name': 'Kekzal',
                'docs': [
                    'project-kekzal.md'
                ]
            },
            {
                'display_name': 'Memetrex',
                'docs': [
                    'project-memetrex.md'
                ]
            },
            {
                'display_name': 'PepeTrak',
                'docs': [
                    'project-pepetrak.md'
                ]
            },
            {
                'display_name': 'MemeGen',
                'docs': [
                    'project-memegen.md'
                ]
            },
            {
                'display_name': 'Neuro-kek',
                'docs': [
                    'project-neurokek.md'
                ]
            },
            {
                'display_name': 'Pepe Corp. (company)',
                'docs': [
                    'org-about_the_company.md',
                    'org-board_of_directors.md',
                    'org-company_story.md',
                    'org-corporate_philosophy.md',
                    'org-customer_support.md',
                    'org-earnings_fy2023.md',
                    'org-management_team.md' 
                ]
            }
        ]
    },
    {
        'display_name': 'Umbrella Corp',
        'namespace': 'acme',
        'projects': [
            {'display_name': 'T-Virus'},
            {'display_name': 'G-Virus'},
            {'display_name': 'Umbrella Corp. (company)'}
        ]
    },
    {
        'display_name': 'Cyberdine Systems',
        'namespace': 'cyberdine',
        'projects': [
            {'display_name': 'Skynet'},
            {'display_name': 'Cyberdine Systems (company)'}
        ]
    },
    {
        'display_name': 'Bluth Companies',
        'namespace': 'bluth',
        'projects': [
            {'display_name': 'Bluth Company (company)'}
        ]
    },
    {
        'display_name': 'Evil Corp',
        'namespace': 'evil',
        'projects': [
            {'display_name': 'E-Coin'},
            {'display_name': 'E-Corp Power'},
            {'display_name': 'Bank of E Network'},
            {'display_name': 'E Corp Labs'},
            {'display_name': 'Evil Corp (company)'}
        ]
    }
]

training_data_path = os.path.join(os.path.dirname(__file__), f'{FILE_UPLOAD_PATH}/training_data')

for org in organizations:

    org_obj = create_org_by_org_or_uuid(
        display_name=org['display_name'],
        namespace=org['namespace']
    )
    logger.debug(f'🏠  Created organization: {org_obj.display_name}')

    if 'projects' not in org:
        continue

    for project in org['projects']:
        project['organization'] = org_obj

        project_obj = create_project_by_org(
            organization_id=org_obj,
            display_name=project['display_name']
        )
        logger.debug(f'🗂️  Created project: {project_obj.display_name}')

        project_uuid = str(project_obj.uuid)
        org_uuid = str(org_obj.uuid)

        # if the directory does not exist, create it
        if not os.path.exists(os.path.join(FILE_UPLOAD_PATH, org_uuid, project_uuid)):
            os.mkdir(os.path.join(FILE_UPLOAD_PATH, org_uuid, project_uuid))

        if 'docs' not in project:
            continue

        for doc in project['docs']:
            file_path = os.path.join(training_data_path, doc)

            # check if file exists
            if os.path.isfile(file_path):
                file_hash = get_file_hash(file_path)
                create_document_by_file_path(
                    organization=org_obj,
                    project=project_obj,
                    file_path=file_path,
                    file_hash=file_hash
                )
                logger.info(f'  ✅  Created document: {doc}')
            else:
                logger.error(f' ❌  Document not found: {doc}')