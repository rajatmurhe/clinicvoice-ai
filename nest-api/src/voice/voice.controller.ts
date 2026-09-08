import { Controller, Post, UseInterceptors, UploadedFile } from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import axios from 'axios';
import FormData from 'form-data';

@Controller('voice')
export class VoiceController {
  @Post('query')
  @UseInterceptors(FileInterceptor('audio'))
  async query(@UploadedFile() file: Express.Multer.File) {
    const formData = new FormData();
    formData.append('audio', file.buffer, {
      filename: file.originalname || 'recording.webm',
      contentType: file.mimetype,
    });

    const response = await axios.post(
      'http://localhost:5050/api/voice/query',
      formData,
      { headers: formData.getHeaders() }
    );

    return response.data;
  }
}
