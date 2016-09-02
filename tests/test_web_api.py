from hashlib import md5
from mock import patch
from os import path as ospath
from regparser.web.jobs.models import job_status_values
from regparser.web.jobs.utils import (
    eregs_site_api_url,
    file_url,
    status_url
)
from regparser.web.jobs.views import FileUploadView as PatchedFileUploadView
from rest_framework.test import APITestCase
from tempfile import NamedTemporaryFile
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

fake_pipeline_id = "f726e1e0-d43c-4eb7-9274-681ddaba427a"
fake_email_id = "4774f0f6-b53e-4b34-821e-fc8ae5e113fe"


def fake_add_redis_data_to_job_data(job_data):
    return job_data


def fake_delete_eregs_job(job_id):
    return None


def fake_redis_job(args, timeout=60*30, result_ttl=-1):
    return type("FakeRedisJob", (object, ), {"id": fake_pipeline_id})


def fake_queue_email(job, statusurl, email_address):
    return fake_email_id


# Even though these functions are in the ``utils`` module, the code paths we're
# following mean we're encountering them in the ``views`` namespace:
@patch("regparser.web.jobs.views.add_redis_data_to_job_data",
       fake_add_redis_data_to_job_data)
@patch("regparser.web.jobs.views.delete_eregs_job", fake_delete_eregs_job)
@patch("regparser.web.jobs.views.queue_eregs_job", fake_redis_job)
@patch("regparser.web.jobs.views.queue_notification_email", fake_queue_email)
class PipelineJobTestCase(APITestCase):

    defaults = {
        "clear_cache": False,
        "destination": eregs_site_api_url,
        "use_uploaded_metadata": None,
        "use_uploaded_regulation": None,
        "regulation_url": "",
        "status": "received"
    }

    def _postjson(self, data):
        return self.client.post("/rp/job/pipeline/", data, format="json")

    def _stock_response_check(self, expected, actual):
        """
        Since we're using a lot of fake values, the tests for them will always
        be the same.
        """
        for key in expected:
            self.assertEqual(expected[key], actual[key])
        self.assertIn(actual["status"], job_status_values)

    def test_create_ints(self):
        data = {
            "cfr_title": 0,
            "cfr_part": 0,
            "notification_email": "test@example.com"
        }
        response = self._postjson(data)

        expected = {k: data[k] for k in data}
        expected.update(self.defaults)
        expected["url"] = status_url(fake_pipeline_id, sub_path="pipeline/")
        self._stock_response_check(expected, response.data)
        return expected

    def test_create_strings(self):
        data = {
            "cfr_title": "0",
            "cfr_part": "0",
            "notification_email": "test@example.com"
        }
        response = self._postjson(data)

        expected = {k: data[k] for k in data}
        expected.update(self.defaults)
        # Even if the input is a str, the return values should be ints:
        expected["cfr_title"] = int(expected["cfr_title"])
        expected["cfr_part"] = int(expected["cfr_part"])
        expected["url"] = status_url(fake_pipeline_id, sub_path="pipeline/")
        self._stock_response_check(expected, response.data)

    def test_create_with_missing_fields(self):
        data = {"cfr_part": "0"}
        response = self._postjson(data)

        self.assertEqual(400, response.status_code)
        self.assertEqual({"cfr_title": ["This field is required."]},
                         response.data)

        data = {"cfr_title": "0"}
        response = self._postjson(data)

        self.assertEqual(400, response.status_code)
        self.assertEqual({"cfr_part": ["This field is required."]},
                         response.data)

        response = self.client.get("/rp/job/pipeline/", format="json")
        self.assertEqual(0, len(response.data))

    def test_create_and_read(self):
        expected = self.test_create_ints()

        url = urlparse(expected["url"])
        response = self.client.get(url.path, format="json")
        self._stock_response_check(expected, response.data)

        response = self.client.get("/rp/job/pipeline/", format="json")
        self.assertEqual(1, len(response.data))
        self._stock_response_check(expected, response.data[0])

    def test_create_delete_and_read(self):
        expected = self.test_create_ints()

        url = urlparse(expected["url"])
        response = self.client.delete(url.path, format="json")
        self.assertEqual(204, response.status_code)

        response = self.client.get(url.path, format="json")
        self.assertEqual(404, response.status_code)

        response = self.client.get("/rp/job/pipeline/", format="json")
        self.assertEqual(0, len(response.data))


class RegulationFileTestCase(APITestCase):

    file_contents = "123"

    def __init__(self, *args, **kwargs):
        self.hashed_contents = md5(self.file_contents).hexdigest()
        super(RegulationFileTestCase, self).__init__(*args, **kwargs)

    def test_create_file(self):
        with NamedTemporaryFile(suffix=".xml", delete=True) as tmp:
            tmp.write(self.file_contents)
            tmp_name = ospath.split(tmp.name)[-1]
            tmp.seek(0)
            response = self.client.post(
                "/rp/job/upload/", {"file": tmp})
        self.assertEquals(201, response.status_code)
        data = response.data
        self.assertEquals(self.hashed_contents, data["hexhash"])
        self.assertEquals(tmp_name, data["filename"])
        self.assertEquals("File contents not shown.", data["contents"])
        self.assertEquals(file_url(self.hashed_contents), data["url"])
        return response

    def test_reject_duplicates(self):
        self.test_create_file()
        with NamedTemporaryFile(suffix=".xml", delete=True) as tmp:
            tmp.write(self.file_contents)
            tmp.seek(0)
            response = self.client.post(
                "/rp/job/upload/", {"file": tmp})
        self.assertEquals(400, response.status_code)
        self.assertIn("error", response.data)
        self.assertEquals("File already present.", response.data["error"])

    def test_reject_large(self):
        with patch("regparser.web.jobs.views.FileUploadView",
                   new=PatchedFileUploadView) as p:
            p.size_limit = 10000
            with NamedTemporaryFile(suffix=".xml", delete=True) as tmp:
                tmp.write(self.file_contents)
                tmp.seek(0)
                response = self.client.post(
                    "/rp/job/upload/", {"file": tmp})
            self.assertEquals(201, response.status_code)

            with NamedTemporaryFile(suffix=".xml", delete=True) as tmp:
                contents = "123" * 100001
                tmp.write(contents)
                tmp.seek(0)
                response = self.client.post(
                    "/rp/job/upload/", {"file": tmp})
            self.assertEquals(400, response.status_code)
            self.assertEquals("File too large (10000-byte limit).",
                              response.data["error"])

    def test_create_and_read_and_delete(self):
        expected = self.test_create_file().data
        url = urlparse(expected["url"])
        response = self.client.get(url.path)
        self.assertEquals(self.file_contents, response.content)

        response = self.client.get("/rp/job/upload/", format="json")
        self.assertEquals(1, len(response.data))
        data = response.data[0]
        self.assertEquals("File contents not shown.", data["contents"])
        self.assertEquals(expected["file"], data["file"])
        self.assertEquals(expected["filename"], data["filename"])
        self.assertEquals(self.hashed_contents, data["hexhash"])
        self.assertEquals(url.path, urlparse(data["url"]).path)

        response = self.client.delete(url.path)
        self.assertEqual(204, response.status_code)

        response = self.client.get(url.path)
        self.assertEqual(404, response.status_code)

        response = self.client.get("/rp/job/upload/", format="json")
        data = response.data
        self.assertEquals(0, len(data))


@patch("regparser.web.jobs.views.add_redis_data_to_job_data",
       fake_add_redis_data_to_job_data)
@patch("regparser.web.jobs.views.delete_eregs_job", fake_delete_eregs_job)
@patch("regparser.web.jobs.views.queue_eregs_job", fake_redis_job)
@patch("regparser.web.jobs.views.queue_notification_email", fake_queue_email)
class ProposalPipelineTestCase(APITestCase):

    defaults = {
        "clear_cache": False,
        "destination": eregs_site_api_url,
        "only_latest": True,
        "use_uploaded_metadata": None,
        "use_uploaded_regulation": None,
        "regulation_url": "",
        "status": "received"
    }
    file_contents = "456"

    def __init__(self, *args, **kwargs):
        self.hashed_contents = md5(self.file_contents).hexdigest()
        super(ProposalPipelineTestCase, self).__init__(*args, **kwargs)

    def _create_file(self):
        with NamedTemporaryFile(suffix=".xml") as tmp:
            tmp.write(self.file_contents)
            tmp.seek(0)
            response = self.client.post("/rp/job/upload/", {"file": tmp})
        return response.data

    def _postjson(self, data):
        return self.client.post("/rp/job/proposal-pipeline/", data,
                                format="json")

    def _stock_response_check(self, expected, actual):
        """
        Since we're using a lot of fake values, the tests for them will always
        be the same.
        """
        for key in expected:
            self.assertEqual(expected[key], actual[key])
        self.assertIn(actual["status"], job_status_values)

    def test_create(self):
        file_data = self._create_file()
        data = {
            "file_hexhash": file_data["hexhash"],
            "notification_email": "test@example.com"
        }
        response = self._postjson(data)
        expected = {k: data[k] for k in data}
        expected.update(self.defaults)
        expected["url"] = status_url(fake_pipeline_id,
                                     sub_path="proposal-pipeline/")
        self._stock_response_check(expected, response.data)
        return expected

    def test_create_with_missing_fields(self):
        data = {"notification_email": "test@example.com"}
        response = self._postjson(data)

        self.assertEqual(400, response.status_code)
        self.assertEqual({"file_hexhash": ["This field is required."]},
                         response.data)

    def test_create_and_read_and_delete(self):
        expected = self.test_create()

        url = urlparse(expected["url"])
        response = self.client.get(url.path, format="json")
        self._stock_response_check(expected, response.data)

        response = self.client.get("/rp/job/proposal-pipeline/", format="json")
        self.assertEqual(1, len(response.data))
        self._stock_response_check(expected, response.data[0])

        response = self.client.delete(url.path, format="json")
        self.assertEqual(204, response.status_code)

        response = self.client.get(url.path, format="json")
        self.assertEqual(404, response.status_code)

        response = self.client.get("/rp/job/proposal-pipeline/", format="json")
        self.assertEqual(0, len(response.data))
