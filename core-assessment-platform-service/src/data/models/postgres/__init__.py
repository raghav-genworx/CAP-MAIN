"""PostgreSQL model registry."""

from data.models.postgres.base import Base
from data.models.postgres.core.ai_run_log import AIRunLogModel
from data.models.postgres.core.assessment_question import AssessmentQuestionModel
from data.models.postgres.core.assessment_slot import AssessmentSlotModel
from data.models.postgres.core.assessment_template import AssessmentTemplateModel
from data.models.postgres.core.candidate import CandidateModel
from data.models.postgres.core.candidate_assessment import CandidateAssessmentModel
from data.models.postgres.core.candidate_proctor_event import CandidateProctorEventModel
from data.models.postgres.core.question_bank_question import QuestionBankQuestionModel
from data.models.postgres.core.question_group import QuestionGroupModel
from data.models.postgres.core.recruiter_notification import RecruiterNotificationModel
from data.models.postgres.core.recruiter_notification_setting import (
    RecruiterNotificationSettingModel,
)
from data.models.postgres.core.submission import SubmissionModel
from data.models.postgres.core.user_role import UserRoleModel

__all__ = [
    "AIRunLogModel",
    "AssessmentQuestionModel",
    "AssessmentSlotModel",
    "AssessmentTemplateModel",
    "Base",
    "CandidateAssessmentModel",
    "CandidateProctorEventModel",
    "CandidateModel",
    "QuestionBankQuestionModel",
    "QuestionGroupModel",
    "RecruiterNotificationModel",
    "RecruiterNotificationSettingModel",
    "SubmissionModel",
    "UserRoleModel",
]
