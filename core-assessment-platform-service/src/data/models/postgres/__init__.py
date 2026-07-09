"""PostgreSQL model registry."""

from data.models.postgres.ai_run_log import AIRunLogModel
from data.models.postgres.assessment_question import AssessmentQuestionModel
from data.models.postgres.assessment_slot import AssessmentSlotModel
from data.models.postgres.assessment_template import AssessmentTemplateModel
from data.models.postgres.base import Base
from data.models.postgres.candidate import CandidateModel
from data.models.postgres.candidate_assessment import CandidateAssessmentModel
from data.models.postgres.question_bank_question import QuestionBankQuestionModel
from data.models.postgres.question_group import QuestionGroupModel
from data.models.postgres.recruiter_notification import RecruiterNotificationModel
from data.models.postgres.recruiter_notification_setting import (
    RecruiterNotificationSettingModel,
)
from data.models.postgres.submission import SubmissionModel
from data.models.postgres.user_role import UserRoleModel

__all__ = [
    "AIRunLogModel",
    "AssessmentQuestionModel",
    "AssessmentSlotModel",
    "AssessmentTemplateModel",
    "Base",
    "CandidateAssessmentModel",
    "CandidateModel",
    "QuestionBankQuestionModel",
    "QuestionGroupModel",
    "RecruiterNotificationModel",
    "RecruiterNotificationSettingModel",
    "SubmissionModel",
    "UserRoleModel",
]
